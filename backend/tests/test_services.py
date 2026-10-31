from __future__ import annotations

import asyncio
import pytest

from app.services.event_bus import EventBus
from app.services.generic_device import GenericDevice
from app.services.device_manager import DeviceManager
from app.services.scenario_engine import ScenarioEngine, compare
from app.services.storage import Storage


def test_generic_device_declaration_and_writable_command(tmp_path):
    device = GenericDevice("test_generic", "Тест", [
        {"name": "switch", "title": "Переключатель", "control": "switch",
         "management": "rw", "kind": "capability", "value": 0},
        {"name": "temperature", "title": "Температура", "control": "number",
         "management": "r", "kind": "property", "value": 21},
    ])
    assert {row["name"] for row in device.declaration()} >= {"switch", "temperature"}
    device.on_command("switch", 1)
    assert device.signals["switch"].value == 1
    assert device.signals["temperature"].value == 21

    async def readonly_is_rejected():
        manager = DeviceManager(Storage(tmp_path), EventBus())
        manager.devices["test_generic"] = device
        with pytest.raises(PermissionError):
            await manager.command("test_generic", "temperature", 25)
    asyncio.run(readonly_is_rejected())


def test_predicate_comparison():
    assert compare(22, ">", 20)
    assert compare(1, "==", 1)
    assert not compare(0, "==", 1)


def test_scenario_validation_accepts_demo_and_rejects_readonly_action():
    from app.main import validate_scenario
    good = {"trigger": {"device_id": "leak_1", "signal": "leak"},
            "actions": [{"device_id": "light_1", "signal": "lamp", "value": 1}]}
    validate_scenario(good)
    bad = {"trigger": good["trigger"],
           "actions": [{"device_id": "light_1", "signal": "power_w", "value": 1}]}
    with pytest.raises(ValueError):
        validate_scenario(bad)


def test_leak_to_light_scenario(tmp_path):
    async def run():
        bus = EventBus()
        storage = Storage(tmp_path)
        manager = DeviceManager(storage, bus)
        scenario = {"id": "demo", "title": "Протечка → свет", "enabled": True,
                    "trigger": {"device_id": "leak_1", "signal": "leak", "operator": "==", "value": 1},
                    "actions": [{"device_id": "light_1", "signal": "lamp", "value": 1}]}
        storage.write("scenarios.json", [scenario])
        engine = ScenarioEngine(manager, storage, bus)
        engine.start()
        await asyncio.sleep(0)
        await manager.simulate("leak_1", "leak", 1)
        await asyncio.sleep(.05)
        assert manager.get_state("light_1")["lamp"] == 1
        assert any(row["node_id"] == "success" for row in engine.logs)
        await engine.stop()
    asyncio.run(run())


def test_api_local_demo_and_persistence(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main as api
    storage = Storage(tmp_path)
    monkeypatch.setattr(api, "storage", storage)
    monkeypatch.setattr(api.manager, "storage", storage)
    monkeypatch.setattr(api.engine, "storage", storage)
    storage.write("scenarios.json", [{
        "id": "api_demo", "title": "Протечка → свет", "enabled": True,
        "trigger": {"device_id": "leak_1", "signal": "leak", "operator": "==", "value": 1},
        "actions": [{"device_id": "light_1", "signal": "lamp", "value": 1}],
    }])
    with TestClient(api.app) as client:
        response = client.get("/api/devices")
        assert response.status_code == 200
        assert len(response.json()) >= 5
        created = client.post("/api/generic-devices", json={
            "title": "Датчик гаража",
            "signals": [{"name": "opened", "title": "Открыто", "control": "switch",
                         "management": "rw", "kind": "capability", "value": 0}],
        })
        assert created.status_code == 200
        generic_id = created.json()["id"]
        assert client.get("/api/devices").json()[-1]["id"] == generic_id
        assert any(row["id"] == generic_id for row in Storage(tmp_path).read("generic_devices.json", []))
        with client.websocket_connect("/ws/events") as socket:
            response = client.post("/api/devices/leak_1/simulate", json={"signal": "leak", "value": 1})
            assert response.status_code == 200
            assert socket.receive_json()["type"] == "signal"
        for _ in range(30):
            if client.get("/api/devices/light_1/state").json()["lamp"] == 1:
                break
            import time
            time.sleep(.01)
        assert client.get("/api/devices/light_1/state").json()["lamp"] == 1
