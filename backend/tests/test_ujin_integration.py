import asyncio
import copy
import json

import pytest

from app.services.device_manager import DeviceManager
from app.services.event_bus import EventBus
from app.services.scenario_compiler import compile_autoscript
from app.services.scenario_engine import ScenarioEngine
from app.services.storage import Storage
from app.services.ujin_adapter import UjinAdapter, UjinError
from app.services.ujin_bridge import UjinBridge, tasks


class Platform:
    configured = True
    enabled = False
    model_class = "integrations_devices"
    safe_message = staticmethod(str)

    def __init__(self):
        self.info = {"error": 0, "data": {"signals": []}}
        self.published = []
        self.fail_publish = False
        self.fail_read = False

    def status(self):
        return {"configured": True, "enabled": self.enabled, "mode": "LIVE" if self.enabled else "LOCAL"}

    def read_device(self, serial):
        if self.fail_read:
            raise UjinError("network unavailable")
        return copy.deepcopy(self.info)

    def publish(self, rows, new_short=(), serialnumber=""):
        if self.fail_publish:
            raise UjinError("publish unavailable")
        self.published.append((copy.deepcopy(rows), copy.deepcopy(new_short)))
        for row in rows:
            signals = self.info["data"]["signals"]
            current = next((s for s in signals if s["name"] == row["s"]), None)
            if current is None:
                current = {"name": row["s"], "state": {}}
                signals.append(current)
            current.setdefault("state", {})["value"] = row["v"]
        return {"error": 0}


def setup(tmp_path):
    storage, bus, remote = Storage(tmp_path), EventBus(), Platform()
    manager = DeviceManager(storage, bus)
    storage.write("ujin_bindings.json", {"light_1": {"serialnumber": "17048733610013356", "ext_guid": "test_light", "signal_map": {}}})
    return UjinBridge(manager, storage, bus, remote), remote


def task_info(value, stamp=10, name="integrations_devices_lamp"):
    return {"error": 0, "data": {"signals": [{"name": name, "signal_task_value": value,
        "signal_task_dt": stamp, "state": {"value": 0}}]}}


def test_snapshot_has_ext_class_full_names_zero_workaround_and_bootstrap(tmp_path):
    bridge, remote = setup(tmp_path)
    asyncio.run(bridge.sync_once())
    rows, short = remote.published[0]
    lamp = next(row for row in rows if row["s"] == "integrations_devices_lamp")
    assert lamp == {"sn": "test_light", "s": "integrations_devices_lamp", "v": .001, "c": "integrations_devices"}
    assert any(row["s"] == "lamp" for row in short)
    assert not any(row["s"].endswith("_fw") for row in rows)


@pytest.mark.parametrize("value", [0, "0", 1, "1", .001])
def test_remote_task_applies_and_is_deduplicated_across_restarts(tmp_path, value):
    bridge, remote = setup(tmp_path)
    remote.info = task_info(value)
    async def run():
        await bridge.sync_once()
        assert bridge.manager.get_state("light_1")["lamp"] == (0 if float(value) in (0, .001) else 1)
        assert len([log for log in bridge.logs if log["kind"] == "command"]) == 1
        ticks = bridge.manager.get("light_1").tick_count
        await bridge.sync_once()
        assert bridge.manager.get("light_1").tick_count == ticks
        restarted = UjinBridge(bridge.manager, bridge.storage, bridge.bus, remote)
        await restarted.sync_once()
        assert bridge.manager.get("light_1").tick_count == ticks
    asyncio.run(run())


def test_same_value_new_timestamp_is_a_new_command(tmp_path):
    bridge, remote = setup(tmp_path)
    async def run():
        remote.info = task_info(1, stamp=10)
        await bridge.sync_once()
        remote.info = task_info(1, stamp=11)
        await bridge.sync_once()
        assert len([log for log in bridge.logs if log["kind"] == "command"]) == 2
    asyncio.run(run())


def test_failed_ack_does_not_reexecute_successful_command(tmp_path):
    bridge, remote = setup(tmp_path)
    async def run():
        remote.info = task_info(1)
        remote.fail_publish = True
        assert (await bridge.sync_once())["connected"] is False
        ticks = bridge.manager.get("light_1").tick_count
        assert bridge._pending["light_1"]
        remote.fail_publish = False
        assert (await bridge.sync_once())["connected"] is True
        assert not bridge._pending["light_1"]
        assert bridge.manager.get("light_1").tick_count == ticks
    asyncio.run(run())


def test_invalid_command_is_not_marked_successful_or_acknowledged(tmp_path):
    bridge, remote = setup(tmp_path)
    remote.info = task_info(123)
    result = asyncio.run(bridge.sync_once())
    assert result["connected"] is False
    assert not bridge.bindings["light_1"].get("seen_tasks")
    assert not remote.published
    assert bridge.manager.get_state("light_1")["lamp"] == 0


def test_readonly_local_signals_cannot_be_written_by_platform(tmp_path):
    bridge, remote = setup(tmp_path)
    remote.info = task_info(999, name="integrations_devices_power_w")
    asyncio.run(bridge.sync_once())
    assert bridge.manager.get_state("light_1")["power_w"] == 0
    assert not any(log["kind"] == "command" for log in bridge.logs)


def test_network_recovery_and_one_bad_device_does_not_stop_the_others(tmp_path):
    bridge, remote = setup(tmp_path)
    async def run():
        remote.fail_read = True
        assert (await bridge.sync_once())["connected"] is False
        remote.fail_read = False
        assert (await bridge.sync_once())["connected"] is True
    asyncio.run(run())


def test_event_transitions_are_published_in_order(tmp_path):
    bridge, remote = setup(tmp_path)
    bridge.bindings["leak_1"] = {"serialnumber": "2", "ext_guid": "test_leak"}
    async def run():
        bridge._queue = bridge.bus.subscribe()
        listener = asyncio.create_task(bridge._listen())
        try:
            await bridge.manager.simulate("leak_1", "leak", 1)
            await bridge.manager.simulate("leak_1", "leak", 0)
            await asyncio.sleep(0)
            await bridge.sync_once()
        finally:
            listener.cancel()
            await asyncio.gather(listener, return_exceptions=True)
    asyncio.run(run())
    values = [row["v"] for batch, _ in remote.published for row in batch
              if row["sn"] == "test_leak" and row["s"] == "integrations_devices_leak"]
    assert values[:2] == [1, .001]


def test_platform_event_runs_local_scenario_and_result_is_published(tmp_path):
    bridge, remote = setup(tmp_path)
    bridge.storage.write("scenarios.json", [{"id": "remote", "enabled": True,
        "trigger": {"device_id": "light_1", "signal": "lamp", "value": 1},
        "actions": [{"device_id": "barrier_1", "signal": "open_cmd", "value": 1}]}])
    bridge.bindings["barrier_1"] = {"serialnumber": "2", "ext_guid": "test_barrier"}
    engine = ScenarioEngine(bridge.manager, bridge.storage, bridge.bus)
    async def run():
        engine.start()
        await asyncio.sleep(0)
        remote.info = task_info(1)
        await bridge.sync_once()
        await asyncio.sleep(.01)
        assert any(log["node_id"] == "success" for log in engine.logs)
        await engine.stop()
    asyncio.run(run())


def test_api_error_is_not_reported_as_success_and_secrets_are_redacted(monkeypatch):
    adapter = UjinAdapter()
    adapter.ust, adapter.password = "ust-sensitive", "secret"
    with pytest.raises(UjinError, match="отклонено"):
        adapter.checked({"error": 1, "message": "отклонено"})
    assert "secret" not in adapter.safe_message("secret ust-sensitive")
    public = adapter.public({"token": "sensitive", "data": {"authKey": "secret", "value": 1}})
    assert public == {"data": {"value": 1}}


def test_compiler_uses_remote_ids_and_rejects_silent_loss_of_actions():
    scenario = {"title": "test", "trigger": {"device_id": "leak_1", "signal": "leak", "value": 1},
                "actions": [{"device_id": "light_1", "signal": "lamp", "value": 1}]}
    bindings = {"leak_1": {"serialnumber": "100"}, "light_1": {"serialnumber": "200"}}
    assert compile_autoscript(scenario, bindings)["when"] == "when:device-100:leak=1"
    scenario["actions"].append(scenario["actions"][0])
    with pytest.raises(ValueError):
        compile_autoscript(scenario, bindings)


def test_bms_nested_task_projection_and_zero():
    result = list(tasks({"data": {"signals": [{"name": "lamp", "state": {"task": 0, "value": 1}}]}}))
    assert result[0][:2] == ("lamp", 0)


def test_old_timestamp_is_not_replayed(tmp_path):
    bridge, remote = setup(tmp_path)
    async def run():
        remote.info = task_info(1, stamp=20)
        await bridge.sync_once()
        remote.info = task_info(0, stamp=19)
        await bridge.sync_once()
        assert bridge.manager.get_state("light_1")["lamp"] == 1
    asyncio.run(run())


def test_silent_platform_drop_is_reported_as_failure(tmp_path):
    bridge, remote = setup(tmp_path)
    remote.publish = lambda *args, **kwargs: {"error": 0}
    result = asyncio.run(bridge.sync_once())
    assert result["connected"] is False
    assert "не подтвердил" in result["bindings"][0]["error"]
    assert not bridge._sent["light_1"]


def test_short_bms_names_are_accepted_for_commands(tmp_path):
    bridge, remote = setup(tmp_path)
    remote.info = task_info(1, name="lamp")
    asyncio.run(bridge.sync_once())
    assert bridge.manager.get_state("light_1")["lamp"] == 1


def test_device_failure_does_not_block_other_devices(tmp_path):
    bridge, remote = setup(tmp_path)
    bridge.bindings["leak_1"] = {"serialnumber": "2", "ext_guid": "test_leak"}
    read = remote.read_device
    remote.read_device = lambda serial: read(serial) if serial == "2" else (_ for _ in ()).throw(UjinError("offline"))
    asyncio.run(bridge.sync_once())
    assert bridge.device_status["light_1"]["connected"] is False
    assert bridge.device_status["leak_1"]["connected"] is True


def test_authentication_accepts_employee_nested_token(monkeypatch):
    from ujin_client import UjinClient
    monkeypatch.setenv("UJIN_LOGIN", "employee")
    monkeypatch.setenv("UJIN_PASSWORD", "test-password")
    monkeypatch.setenv("UJIN_APARTMENT_ID", "1")
    monkeypatch.setenv("UJIN_BASE_URL", "https://example.test/api/")
    monkeypatch.setattr(UjinClient, "authenticate", lambda self, login, password, app: {
        "error": 0, "data": {"user": {"token": "ust-test"}}})
    adapter = UjinAdapter()
    assert adapter.client().ust == "ust-test"
    assert adapter.client().base_url == "https://example.test"
    assert "ust-test" not in json.dumps(adapter.status())
    assert "ust-test" not in json.dumps(adapter.public({"url": "https://example.test/?token=ust-test"}))


def test_rest_sync_updates_the_same_devices_and_websocket(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main as api
    bridge, remote = setup(tmp_path)
    for name, value in {"manager": bridge.manager, "bridge": bridge, "ujin": remote,
                        "bus": bridge.bus, "storage": bridge.storage,
                        "engine": ScenarioEngine(bridge.manager, bridge.storage, bridge.bus)}.items():
        monkeypatch.setattr(api, name, value)
    remote.info = task_info(1)
    with TestClient(api.app) as client:
        with client.websocket_connect("/ws/events") as socket:
            response = client.post("/api/live/sync")
            assert response.status_code == 200
            assert response.json()["connected"] is True
            assert socket.receive_json()["type"] == "signal"
        assert client.get("/api/devices/light_1/state").json()["lamp"] == 1


def test_transport_uses_json_and_query_auth_for_group(monkeypatch):
    import io
    import urllib.parse
    import urllib.request
    from ujin_client import UjinClient
    requests = []
    def request(req, timeout):
        requests.append(req)
        return io.BytesIO(b'{"error": 0}')
    monkeypatch.setattr(urllib.request, "urlopen", request)
    client = UjinClient("https://example.test/api", ust="ust-test", apartment_id="1", dry_run=False)
    client._journal = lambda *_: None
    rows = [{"sn": "external", "s": "integrations_devices_lamp", "v": .001, "c": "integrations_devices"}]
    client.publish_group(rows, serialnumber="17048733610013356")
    req = requests[0]
    assert req.get_header("Content-type") == "application/json"
    assert json.loads(req.data) == {"data": rows}
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
    assert query == {"token": ["ust-test"], "apartment_id": ["1"], "serialnumber": ["17048733610013356"]}
    assert "/api/api/" not in req.full_url


def test_bootstrap_api_error_aborts_value_phase(monkeypatch):
    from ujin_client import UjinClient
    client = UjinClient(dry_run=False)
    calls = []
    def reject(path, payload, serialnumber=""):
        calls.append(payload)
        return {"error": 1, "message": "dictionary unavailable"}
    monkeypatch.setattr(client, "_post_json", reject)
    assert client.publish_group([{"s": "full"}], new_short=[{"s": "short"}])["error"] == 1
    assert len(calls) == 1


def test_missing_credentials_file_keeps_local_mode_available(monkeypatch, tmp_path):
    monkeypatch.setenv("UJIN_ACCESS_FILE", str(tmp_path / "missing.json"))
    adapter = UjinAdapter()
    assert not adapter.configured
    assert "UJIN_ACCESS_FILE" in adapter.status()["message"]


def test_binding_storage_recovers_from_temporary_windows_lock(monkeypatch, tmp_path):
    import os
    real_replace, attempts = os.replace, []
    def briefly_locked(src, dst):
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError("temporary file lock")
        return real_replace(src, dst)
    monkeypatch.setattr(os, "replace", briefly_locked)
    storage = Storage(tmp_path)
    storage.write("ujin_bindings.json", {"light_1": {"serialnumber": "1"}})
    assert storage.read("ujin_bindings.json", {})["light_1"]["serialnumber"] == "1"
    assert len(attempts) == 3
