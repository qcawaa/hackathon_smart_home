import uuid

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_engine, get_manager, get_storage
from app.api.v1._helpers import scenario_rows, validate_scenario
from app.core.errors import error
from app.services.device_manager import DeviceManager
from app.services.quick_scenarios import QUICK_SCENARIOS, run_quick_scenario
from app.services.scenario_engine import ScenarioEngine
from app.services.storage import Storage

router = APIRouter()


@router.get("/scenarios")
async def scenarios(storage: Storage = Depends(get_storage)):
    return scenario_rows(storage)


@router.get("/quick-scenarios")
async def quick_scenarios():
    return list(QUICK_SCENARIOS.values())


@router.post("/quick-scenarios/{scenario_id}/run")
async def run_quick(scenario_id: str, manager: DeviceManager = Depends(get_manager),
                    engine: ScenarioEngine = Depends(get_engine)):
    if scenario_id not in QUICK_SCENARIOS:
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    return await run_quick_scenario(scenario_id, manager, engine)


@router.delete("/quick-scenarios/{scenario_id}")
async def delete_quick(scenario_id: str):
    if scenario_id not in QUICK_SCENARIOS:
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    raise error(403, "PROTECTED_SCENARIO", "Закреплённый сценарий нельзя удалить")


@router.post("/scenarios")
async def create_scenario(body: dict, manager: DeviceManager = Depends(get_manager),
                          storage: Storage = Depends(get_storage)):
    if body.get("id") in QUICK_SCENARIOS:
        raise error(403, "PROTECTED_SCENARIO", "Закреплённый сценарий нельзя изменить")
    try:
        validate_scenario(body, manager)
        rows = scenario_rows(storage)
        if not body.get("id"):
            body["id"] = f"scenario_{uuid.uuid4().hex}"
        rows = [row for row in rows if row.get("id") != body["id"]]
        rows.append(body)
        storage.write("scenarios.json", rows)
        return body
    except ValueError as exc:
        raise error(400, "INVALID_SCENARIO", str(exc))


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str, storage: Storage = Depends(get_storage)):
    row = next((row for row in scenario_rows(storage) if row.get("id") == scenario_id), None)
    if not row:
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    return row


@router.put("/scenarios/{scenario_id}")
async def update_scenario(scenario_id: str, body: dict,
                          manager: DeviceManager = Depends(get_manager),
                          storage: Storage = Depends(get_storage)):
    if scenario_id in QUICK_SCENARIOS:
        raise error(403, "PROTECTED_SCENARIO", "Закреплённый сценарий нельзя изменить")
    body["id"] = scenario_id
    try:
        validate_scenario(body, manager)
    except ValueError as exc:
        raise error(400, "INVALID_SCENARIO", str(exc))
    rows = scenario_rows(storage)
    if not any(row.get("id") == scenario_id for row in rows):
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    rows = [body if row.get("id") == scenario_id else row for row in rows]
    storage.write("scenarios.json", rows)
    return body


@router.delete("/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: str, engine: ScenarioEngine = Depends(get_engine),
                          storage: Storage = Depends(get_storage)):
    if scenario_id in QUICK_SCENARIOS:
        raise error(403, "PROTECTED_SCENARIO", "Закреплённый сценарий нельзя удалить")
    rows = scenario_rows(storage)
    if not any(row.get("id") == scenario_id for row in rows):
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    storage.write("scenarios.json", [row for row in rows if row.get("id") != scenario_id])
    engine._trigger_active.pop(scenario_id, None)
    return {"ok": True}


@router.post("/scenarios/{scenario_id}/validate")
async def validate_by_id(scenario_id: str, manager: DeviceManager = Depends(get_manager),
                         storage: Storage = Depends(get_storage)):
    scenario = next((row for row in scenario_rows(storage) if row.get("id") == scenario_id), None)
    if not scenario:
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    try:
        validate_scenario(scenario, manager)
        return {"valid": True}
    except ValueError as exc:
        raise error(400, "INVALID_SCENARIO", str(exc))


@router.post("/scenarios/{scenario_id}/test")
async def test_scenario(scenario_id: str, manager: DeviceManager = Depends(get_manager),
                        storage: Storage = Depends(get_storage)):
    scenario = next((row for row in scenario_rows(storage) if row.get("id") == scenario_id), None)
    if not scenario:
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    old = scenario.get("enabled", False)
    scenario["enabled"] = True
    storage.write("scenarios.json", scenario_rows(storage))
    trigger = scenario["trigger"]
    result = await manager.simulate(trigger["device_id"], trigger["signal"], trigger.get("value", 1))
    scenario["enabled"] = old
    storage.write("scenarios.json", scenario_rows(storage))
    return result


@router.post("/scenarios/{scenario_id}/enable")
@router.post("/scenarios/{scenario_id}/disable")
async def set_scenario_enabled(scenario_id: str, request: Request,
                               storage: Storage = Depends(get_storage)):
    enabled = request.url.path.endswith("/enable")
    rows = scenario_rows(storage)
    scenario = next((row for row in rows if row.get("id") == scenario_id), None)
    if not scenario:
        raise error(404, "SCENARIO_NOT_FOUND", "Сценарий не найден")
    scenario["enabled"] = enabled
    storage.write("scenarios.json", rows)
    return scenario