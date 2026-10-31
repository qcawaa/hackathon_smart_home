"""Verify real telemetry readback; --command also tests and restores a light command."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / "backend" / ".env")
sys.path.insert(0, str(ROOT / "backend"))
from app.services.device_manager import DeviceManager
from app.services.event_bus import EventBus
from app.services.storage import Storage
from app.services.ujin_adapter import UjinAdapter
from app.services.ujin_bridge import UjinBridge, signal_rows, now


async def verify(command=False):
    storage, bus, adapter = Storage(ROOT / "data"), EventBus(), UjinAdapter()
    manager = DeviceManager(storage, bus)
    bridge = UjinBridge(manager, storage, bus, adapter)
    result = {"time": now(), "base_url": adapter.base, "devices": {}}
    status = await bridge.sync_once()
    result["exchange_errors"] = {row["device_id"]: row["error"] for row in status["bindings"] if row.get("error")}
    for device_id, binding in bridge.bindings.items():
        try:
            rows = signal_rows(await asyncio.to_thread(adapter.read_device, binding["serialnumber"]))
            actual = {row["name"]: (row.get("state") or {}).get("value") for row in rows}
            expected = {bridge.remote_name(binding, name): bridge.wire(sig.value)
                        for name, sig in manager.get(device_id).signals.items()
                        if sig.kind != "system" and sig.publishable and bridge.wire(sig.value) is not None}
            matches = {name: actual.get(name, actual.get(name.removeprefix(adapter.model_class + "_"))) is not None
                       and float(actual.get(name, actual.get(name.removeprefix(adapter.model_class + "_")))) == float(value)
                       for name, value in expected.items()}
            readonly = [row["name"] for row in rows if (row.get("state") or {}).get("readonly")]
            result["devices"][device_id] = {"verified": bool(matches) and all(matches.values()),
                                            "signals": matches, "readonly": readonly}
        except Exception as exc:
            result["devices"][device_id] = {"verified": False, "error": adapter.safe_message(exc)}
    if command and "light_1" in bridge.bindings:
        binding = bridge.bindings["light_1"]
        original = manager.get_state("light_1")["lamp"]
        try:
            await asyncio.to_thread(adapter.send_signal, binding["serialnumber"], bridge.remote_name(binding, "lamp"), 1)
            await bridge.sync_once()
            result["command"] = {"verified": manager.get_state("light_1")["lamp"] == 1,
                                 "local_value": manager.get_state("light_1")["lamp"]}
        except Exception as exc:
            result["command"] = {"verified": False, "error": adapter.safe_message(exc)}
        finally:
            await manager.command("light_1", "lamp", original)
            await bridge.sync_once()
    path = ROOT / "UJIN-LIVE-CHECK.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(row["verified"] for row in result["devices"].values()) and result.get("command", {"verified": True})["verified"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(verify(args.command)))
