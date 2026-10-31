"""Read-only connectivity check without credentials or full API responses."""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / "backend" / ".env")
sys.path.insert(0, str(ROOT / "backend"))
from app.services.ujin_adapter import UjinAdapter
from app.services.ujin_bridge import signal_rows, tasks


def main(device_id=None):
    adapter = UjinAdapter()
    bindings = json.loads((ROOT / "data" / "ujin_bindings.json").read_text(encoding="utf-8"))
    if device_id:
        bindings = {key: row for key, row in bindings.items() if key == device_id}
    if not bindings:
        print("No matching Ujin bindings. Run configure_ujin.py first.")
        return 1
    success = True
    for local_id, binding in bindings.items():
        try:
            info = adapter.read_device(binding["serialnumber"])
            rows = signal_rows(info)
            print(json.dumps({"device_id": local_id, "readable": True,
                              "signals": [row.get("name") or row.get("signal_name") for row in rows
                                          if not str(row.get("name", "")).endswith("token")],
                              "pending_commands": len(list(tasks(info)))}, ensure_ascii=False))
        except Exception as exc:
            success = False
            print(json.dumps({"device_id": local_id, "readable": False,
                              "error": adapter.safe_message(exc)}, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", help="Local device ID, for example light_1")
    args = parser.parse_args()
    raise SystemExit(main(args.device))
