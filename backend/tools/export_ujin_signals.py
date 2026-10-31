"""Export the declarations needed by the team's platform administrator."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.device_manager import DeviceManager
from app.services.event_bus import EventBus
from app.services.storage import Storage

if __name__ == "__main__":
    storage = Storage(ROOT / "data")
    manager = DeviceManager(storage, EventBus())
    bindings = storage.read("ujin_bindings.json", {})
    result = {"model": "parkcloud_device", "class": "integrations_devices", "devices": []}
    for device_id, binding in bindings.items():
        if device_id not in manager.devices:
            continue
        device = manager.get(device_id)
        signals = [{**sig.as_declaration(),
                    "import_name": binding.get("signal_map", {}).get(sig.name, "integrations_devices_" + sig.name),
                    "required_in_bms": True} for sig in device.signals.values() if sig.kind != "system"]
        result["devices"].append({"device_id": device_id, "title": device.title,
                                  "serialnumber": binding["serialnumber"], "ext_guid": binding["ext_guid"],
                                  "signals": signals})
    path = ROOT / "UJIN-REQUIRED-SIGNALS.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(result['devices'])} device declarations to {path.name}")
