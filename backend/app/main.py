from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.device_manager import DeviceManager
from app.services.device_presets import PRESETS, get_preset, list_presets
from app.services.event_bus import EventBus
from app.services.scenario_engine import ScenarioEngine, compare
from app.services.scenario_compiler import compile_autoscript
from app.services.storage import Storage
from app.services.ujin_adapter import UjinAdapter
from app.services.ujin_bridge import UjinBridge

DATA = Path(os.getenv("APP_DATA_DIR", ROOT / "data"))
storage, bus, ujin = Storage(DATA), EventBus(), UjinAdapter()
manager = DeviceManager(storage, bus)
engine = ScenarioEngine(manager, storage, bus)
bridge = UjinBridge(manager, storage, bus, ujin)

@asynccontextmanager
async def lifespan(_app):
    manager.start()
    engine.start()
    bridge.start()
    try:
        yield
    finally:
        await bridge.stop()
        await engine.stop()
        await manager.stop()


app = FastAPI(title="Ujin Smart Home", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class CommandBody(BaseModel):
    signal: str = ""
    value: object


class SimulateBody(BaseModel):
    signal: str
    value: object


class BindingBody(BaseModel):
    # Serial numbers exceed JavaScript's safe integer range. Keep them as strings.
    serialnumber: str = Field(pattern=r"^[0-9]+$", max_length=40)
    ext_guid: str = Field(pattern=r"^[A-Za-z0-9_]+$", max_length=100)
    signal_map: dict[str, str] = Field(default_factory=dict)


class GenericSignal(BaseModel):
    name: str
    title: str
    control: str = "switch"
    management: str = "rw"
    kind: str = "capability"
    value: object = 0
    measure: str = ""
    min: float | None = None
    max: float | None = None
    layout: dict | None = None

    @field_validator("control")
    @classmethod
    def validate_control(cls, value):
        if value not in ("switch", "range", "number", "counter", "list", "text", "push_time", "graph"):
            raise ValueError("Неизвестный тип сигнала")
        return value

    @field_validator("management")
    @classmethod
    def validate_management(cls, value):
        if value not in ("r", "rw", "w"):
            raise ValueError("Неизвестный режим управления")
        return value


class GenericBody(BaseModel):
    id: str | None = None
    title: str = Field(min_length=2, max_length=80)
    signals: list[GenericSignal] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_signal_names(self):
        names = [signal.name for signal in self.signals]
        if len(names) != len(set(names)):
            raise ValueError("Имена сигналов должны быть уникальными")
        return self


class CreatePresetBody(BaseModel):
    type: str
    title: str = Field(min_length=2, max_length=80)


class RenameDeviceBody(BaseModel):
    title: str = Field(min_length=2, max_length=80)


def error(status, code, message):
    return HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


def scenario_rows():
    return storage.read("scenarios.json", [])


def scenarios_using_device(device_id):
    affected = []
    for scenario in scenario_rows():
        parts = [scenario.get("trigger", {})]
        parts.extend(scenario.get("conditions", []))
        if scenario.get("condition"):
            parts.append(scenario["condition"])
        parts.extend(scenario.get("actions", []))
        if scenario.get("action"):
            parts.append(scenario["action"])
        if any(part.get("device_id") == device_id for part in parts):
            affected.append(scenario)
    return affected


def validate_scenario(data):
    trigger = data.get("trigger", {})
    actions = data.get("actions") or [data.get("action") or {}]
    if not actions:
        raise ValueError("Добавьте хотя бы одно действие")
    for part, writable in [(trigger, False), *[(action, True) for action in actions]]:
        dev = manager.devices.get(part.get("device_id", ""))
        if not dev or part.get("signal") not in dev.signals:
            raise ValueError("Устройство или сигнал сценария не найдены")
        if writable and not dev.signals[part["signal"]].writable:
            raise ValueError("Действие должно управлять writable-сигналом")
    conditions = data.get("conditions", [])
    if data.get("condition"):
        conditions = [data["condition"], *conditions]
    for condition in conditions:
        dev = manager.devices.get(condition.get("device_id", ""))
        if not dev or condition.get("signal") not in dev.signals:
            raise ValueError("Сигнал условия не найден")
        if condition.get("operator", "==") not in ("==", "eq", "!=", ">", "<", ">=", "<="):
            raise ValueError("Неизвестный оператор условия")
    if trigger.get("operator", "==") not in ("==", "eq", "!=", ">", "<", ">=", "<="):
        raise ValueError("Неизвестный оператор условия")


@app.exception_handler(HTTPException)
async def http_error_handler(_request, exc):
    from fastapi.responses import JSONResponse
    detail = exc.detail if isinstance(exc.detail, dict) and "error" in exc.detail else {
        "error": {"code": "REQUEST_FAILED", "message": str(exc.detail)}}
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request, _exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=422, content={"error": {"code": "INVALID_REQUEST", "message": "Проверьте заполненные поля"}})


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "ujin-smart-lab"}


@app.get("/api/status")
async def status():
    return {"mode": bridge.status()["mode"], "devices": len(manager.devices), "live": bridge.status()}


@app.get("/api/device-presets")
async def device_presets():
    return list_presets()


@app.get("/api/device-presets/{device_type}")
async def device_preset(device_type: str):
    preset = get_preset(device_type)
    if not preset:
        raise error(404, "PRESET_NOT_FOUND", "Тип устройства не найден")
    return preset


@app.post("/api/devices")
async def create_device(body: CreatePresetBody):
    if body.type not in PRESETS:
        raise error(400, "INVALID_DEVICE_TYPE", "Выберите тип устройства из списка")
    try:
        return manager.create_preset(body.type, body.title.strip())
    except ValueError as exc:
        raise error(400, "INVALID_DEVICE", str(exc))


@app.get("/api/devices")
async def devices():
    return manager.list()


@app.get("/api/devices/{device_id}")
async def device(device_id: str):
    try:
        return manager.details(device_id)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")


@app.put("/api/devices/{device_id}")
async def update_device(device_id: str, body: RenameDeviceBody):
    try:
        if device_id in manager.user_devices:
            return manager.update_preset(device_id, body.title.strip())
        if manager.devices.get(device_id) and manager.devices[device_id].model == "generic_device":
            return manager.rename_generic(device_id, body.title.strip())
        raise KeyError(device_id)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено или его нельзя редактировать")


@app.delete("/api/devices/{device_id}")
async def delete_device(device_id: str):
    affected = scenarios_using_device(device_id)
    if affected:
        titles = "», «".join(row.get("title", "Без названия") for row in affected)
        raise error(409, "DEVICE_IN_USE", f"Устройство используется в сценарии «{titles}». Сначала измените или удалите этот сценарий.")
    try:
        manager.remove_device(device_id)
        await bridge.unbind(device_id)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено или его нельзя удалить")
    return {"ok": True}


@app.get("/api/devices/{device_id}/state")
async def device_state(device_id: str):
    try:
        return manager.get_state(device_id)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")


@app.get("/api/devices/{device_id}/declaration")
async def device_declaration(device_id: str):
    try:
        return manager.get(device_id).declaration()
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")


@app.post("/api/devices/{device_id}/command")
async def device_command(device_id: str, body: CommandBody):
    try:
        return await manager.command(device_id, body.signal, body.value)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")
    except PermissionError as exc:
        raise error(400, "SIGNAL_READ_ONLY", str(exc))
    except ValueError as exc:
        raise error(400, "INVALID_COMMAND", str(exc))


@app.post("/api/devices/{device_id}/command/{signal_name}")
async def device_command_signal(device_id: str, signal_name: str, body: CommandBody):
    try:
        return await manager.command(device_id, signal_name, body.value)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")
    except PermissionError as exc:
        raise error(400, "SIGNAL_READ_ONLY", str(exc))
    except ValueError as exc:
        raise error(400, "INVALID_COMMAND", str(exc))


@app.post("/api/devices/{device_id}/simulate")
async def device_simulate(device_id: str, body: SimulateBody):
    try:
        return await manager.simulate(device_id, body.signal, body.value)
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")
    except ValueError as exc:
        raise error(400, "SIMULATION_NOT_SUPPORTED", str(exc))


@app.get("/api/generic-devices")
async def generic_devices():
    return [row for row in manager.list() if row["model"] == "generic_device"]


@app.post("/api/generic-devices")
async def create_generic(body: GenericBody):
    try:
        return manager.create_generic(body.model_dump())
    except ValueError as exc:
        raise error(400, "INVALID_DEVICE", str(exc))


@app.delete("/api/generic-devices/{device_id}")
async def delete_generic(device_id: str):
    try:
        affected = scenarios_using_device(device_id)
        if affected:
            titles = "», «".join(row.get("title", "Без названия") for row in affected)
            raise error(409, "DEVICE_IN_USE", f"Устройство используется в сценарии «{titles}». Сначала измените или удалите этот сценарий.")
        manager.remove_generic(device_id)
        await bridge.unbind(device_id)
        return {"ok": True}
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")


@app.put("/api/generic-devices/{device_id}")
async def update_generic(device_id: str, body: GenericBody):
    try:
        return manager.update_generic(device_id, body.model_dump())
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Устройство не найдено")
    except ValueError as exc:
        raise error(400, "INVALID_DEVICE", str(exc))


@app.get("/api/scenarios")
async def scenarios():
    return scenario_rows()


@app.post("/api/scenarios")
async def create_scenario(body: dict):
    try:
        validate_scenario(body)
        rows = scenario_rows()
        if not body.get("id"):
            body["id"] = f"scenario_{len(rows) + 1}"
        rows = [row for row in rows if row.get("id") != body["id"]]
        rows.append(body)
        storage.write("scenarios.json", rows)
        return body
    except ValueError as exc:
        raise error(400, "INVALID_SCENARIO", str(exc))


@app.get("/api/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str):
    row = next((row for row in scenario_rows() if row.get("id") == scenario_id), None)
    if not row:
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    return row


@app.put("/api/scenarios/{scenario_id}")
async def update_scenario(scenario_id: str, body: dict):
    body["id"] = scenario_id
    try:
        validate_scenario(body)
    except ValueError as exc:
        raise error(400, "INVALID_SCENARIO", str(exc))
    rows = scenario_rows()
    if not any(row.get("id") == scenario_id for row in rows):
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    rows = [body if row.get("id") == scenario_id else row for row in rows]
    storage.write("scenarios.json", rows)
    return body


@app.delete("/api/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: str):
    rows = scenario_rows()
    if not any(row.get("id") == scenario_id for row in rows):
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    storage.write("scenarios.json", [row for row in rows if row.get("id") != scenario_id])
    return {"ok": True}


@app.post("/api/scenarios/{scenario_id}/validate")
async def validate_by_id(scenario_id: str):
    scenario = next((row for row in scenario_rows() if row.get("id") == scenario_id), None)
    if not scenario:
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    try:
        validate_scenario(scenario)
        return {"valid": True}
    except ValueError as exc:
        raise error(400, "INVALID_SCENARIO", str(exc))


@app.post("/api/scenarios/{scenario_id}/test")
async def test_scenario(scenario_id: str):
    scenario = next((row for row in scenario_rows() if row.get("id") == scenario_id), None)
    if not scenario:
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    old = scenario.get("enabled", False)
    scenario["enabled"] = True
    storage.write("scenarios.json", scenario_rows())
    trigger = scenario["trigger"]
    result = await manager.simulate(trigger["device_id"], trigger["signal"], trigger.get("value", 1))
    scenario["enabled"] = old
    storage.write("scenarios.json", scenario_rows())
    return result


@app.post("/api/scenarios/{scenario_id}/enable")
@app.post("/api/scenarios/{scenario_id}/disable")
async def set_scenario_enabled(scenario_id: str, request: Request):
    enabled = request.url.path.endswith("/enable")
    rows = scenario_rows()
    scenario = next((row for row in rows if row.get("id") == scenario_id), None)
    if not scenario:
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    scenario["enabled"] = enabled
    storage.write("scenarios.json", rows)
    return scenario


@app.get("/api/events")
async def events():
    return engine.logs


@app.get("/api/live/status")
async def live_status():
    return bridge.status()


@app.get("/api/live/bindings")
async def live_bindings():
    return bridge.binding_list()


@app.put("/api/live/bindings/{device_id}")
async def bind_live_device(device_id: str, body: BindingBody):
    try:
        return await bridge.bind(device_id, body.model_dump())
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Эмулятор не найден")
    except ValueError as exc:
        raise error(400, "INVALID_BINDING", str(exc))
    except RuntimeError as exc:
        raise error(502, "UJIN_UNAVAILABLE", ujin.safe_message(exc))


@app.delete("/api/live/bindings/{device_id}")
async def unbind_live_device(device_id: str):
    return await bridge.unbind(device_id)


@app.post("/api/live/sync")
async def sync_live():
    if not ujin.configured:
        raise error(400, "LIVE_NOT_CONFIGURED", "Для LIVE настройте доступы в backend/.env")
    return await bridge.sync_once()


@app.get("/api/live/devices")
async def list_live_devices():
    try:
        return await asyncio.to_thread(ujin.list_devices)
    except Exception as exc:
        raise error(502, "UJIN_UNAVAILABLE", ujin.safe_message(exc))


@app.get("/api/live/devices/{serial}")
async def read_live_device(serial: str):
    if not ujin.configured:
        raise error(400, "LIVE_NOT_CONFIGURED", "Для LIVE настройте доступы в backend/.env")
    try:
        return ujin.public(await asyncio.to_thread(ujin.read_device, serial))
    except Exception as exc:
        raise error(502, "UJIN_UNAVAILABLE", ujin.safe_message(exc))


@app.post("/api/live/devices/{serial}/command")
async def send_live_command(serial: str, body: CommandBody):
    if not ujin.configured:
        raise error(400, "LIVE_NOT_CONFIGURED", "Для LIVE настройте доступы в backend/.env")
    try:
        return await asyncio.to_thread(ujin.send_signal, serial, body.signal, body.value)
    except Exception as exc:
        raise error(502, "UJIN_UNAVAILABLE", ujin.safe_message(exc))


@app.get("/api/live/scenarios")
async def live_scenarios():
    if not ujin.configured:
        return {"configured": False, "items": []}
    try:
        await asyncio.to_thread(ujin.client)
        response = await asyncio.to_thread(ujin.call, "autoscripts_list", ujin.ust)
        return {"configured": True, "items": ujin.public(response)}
    except Exception as exc:
        raise error(502, "UJIN_UNAVAILABLE", ujin.safe_message(exc))


@app.post("/api/live/scenarios/{scenario_id}/deploy")
async def deploy_scenario(scenario_id: str):
    scenario = next((row for row in scenario_rows() if row.get("id") == scenario_id), None)
    if not scenario:
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    if not ujin.configured:
        raise error(400, "LIVE_NOT_CONFIGURED", "Для LIVE настройте доступы в backend/.env")
    try:
        compiled = compile_autoscript(scenario, bridge.bindings, ujin.model_class)
        await asyncio.to_thread(ujin.client)
        response = await asyncio.to_thread(ujin.call, "autoscripts_edit", ujin.ust,
            int(scenario.get("ujin_id") or 0), "trigger", condition=compiled["when"],
            set_signal=compiled["then"], title=compiled["title"])
        remote_id = (response.get("data") or response.get("result") or {}).get("id")
        if remote_id:
            scenario["ujin_id"] = str(remote_id)
            storage.write("scenarios.json", [scenario if row.get("id") == scenario_id else row for row in scenario_rows()])
        return {"compiled": compiled, "response": ujin.public(response)}
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        raise error(400, "LIVE_DEPLOY_FAILED", ujin.safe_message(exc))


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await websocket.accept()
    queue = bus.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)


# Serve the built product from the same origin as REST/WebSocket. Vite remains
# available for development and proxies the same /api and /ws paths.
frontend_dist = ROOT / "frontend" / "dist"
if frontend_dist.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
