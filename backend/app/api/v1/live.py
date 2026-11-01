import asyncio

from fastapi import APIRouter, Depends

from app.api.deps import get_bridge, get_storage, get_ujin
from app.api.v1._helpers import scenario_rows
from app.core.errors import error
from app.schemas.device import CommandBody
from app.schemas.live import BindingBody
from app.services.scenario_compiler import compile_autoscript
from app.services.storage import Storage
from app.services.ujin_adapter import UjinAdapter
from app.services.ujin_bridge import UjinBridge

router = APIRouter()


@router.get("/live/status")
async def live_status(bridge: UjinBridge = Depends(get_bridge)):
    return bridge.status()


@router.get("/live/bindings")
async def live_bindings(bridge: UjinBridge = Depends(get_bridge)):
    return bridge.binding_list()


@router.put("/live/bindings/{device_id}")
async def bind_live_device(device_id: str, body: BindingBody,
                           bridge: UjinBridge = Depends(get_bridge),
                           ujin: UjinAdapter = Depends(get_ujin)):
    try:
        return await bridge.bind(device_id, body.model_dump())
    except KeyError:
        raise error(404, "DEVICE_NOT_FOUND", "Эмулятор не найден")
    except ValueError as exc:
        raise error(400, "INVALID_BINDING", str(exc))
    except RuntimeError as exc:
        raise error(502, "UJIN_UNAVAILABLE", ujin.safe_message(exc))


@router.delete("/live/bindings/{device_id}")
async def unbind_live_device(device_id: str, bridge: UjinBridge = Depends(get_bridge)):
    return await bridge.unbind(device_id)


@router.post("/live/sync")
async def sync_live(bridge: UjinBridge = Depends(get_bridge),
                    ujin: UjinAdapter = Depends(get_ujin)):
    if not ujin.configured:
        raise error(400, "LIVE_NOT_CONFIGURED", "Для LIVE настройте доступы в backend/.env")
    return await bridge.sync_once()


@router.get("/live/devices")
async def list_live_devices(ujin: UjinAdapter = Depends(get_ujin)):
    try:
        return await asyncio.to_thread(ujin.list_devices)
    except Exception as exc:
        raise error(502, "UJIN_UNAVAILABLE", ujin.safe_message(exc))


@router.get("/live/devices/{serial}")
async def read_live_device(serial: str, ujin: UjinAdapter = Depends(get_ujin)):
    if not ujin.configured:
        raise error(400, "LIVE_NOT_CONFIGURED", "Для LIVE настройте доступы в backend/.env")
    try:
        return ujin.public(await asyncio.to_thread(ujin.read_device, serial))
    except Exception as exc:
        raise error(502, "UJIN_UNAVAILABLE", ujin.safe_message(exc))


@router.post("/live/devices/{serial}/command")
async def send_live_command(serial: str, body: CommandBody,
                            ujin: UjinAdapter = Depends(get_ujin)):
    if not ujin.configured:
        raise error(400, "LIVE_NOT_CONFIGURED", "Для LIVE настройте доступы в backend/.env")
    try:
        return await asyncio.to_thread(ujin.send_signal, serial, body.signal, body.value)
    except Exception as exc:
        raise error(502, "UJIN_UNAVAILABLE", ujin.safe_message(exc))


@router.get("/live/scenarios")
async def live_scenarios(ujin: UjinAdapter = Depends(get_ujin)):
    if not ujin.configured:
        return {"configured": False, "items": []}
    try:
        await asyncio.to_thread(ujin.client)
        response = await asyncio.to_thread(ujin.call, "autoscripts_list", ujin.ust)
        return {"configured": True, "items": ujin.public(response)}
    except Exception as exc:
        raise error(502, "UJIN_UNAVAILABLE", ujin.safe_message(exc))


@router.post("/live/scenarios/{scenario_id}/deploy")
async def deploy_scenario(scenario_id: str,
                          bridge: UjinBridge = Depends(get_bridge),
                          ujin: UjinAdapter = Depends(get_ujin),
                          storage: Storage = Depends(get_storage)):
    scenario = next((row for row in scenario_rows(storage) if row.get("id") == scenario_id), None)
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
            storage.write("scenarios.json", [scenario if row.get("id") == scenario_id else row for row in scenario_rows(storage)])
        return {"compiled": compiled, "response": ujin.public(response)}
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        raise error(400, "LIVE_DEPLOY_FAILED", ujin.safe_message(exc))