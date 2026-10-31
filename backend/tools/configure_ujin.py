"""Configure pre-provisioned team devices without copying credentials to the repo."""
import argparse
import json
from pathlib import Path


def configure(access_file, root, live=False):
    access_file = Path(access_file).resolve()
    access = json.loads(access_file.read_text(encoding="utf-8-sig"))
    employee = access.get("employee") or {}
    if not employee.get("login") or not employee.get("password"):
        raise ValueError("В файле доступов нет логина и пароля employee")
    apartment = str(access["team_apartment"])
    path = root / "data" / "ujin_bindings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    bindings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    deleted_path = root / "data" / "deleted_devices.json"
    deleted = json.loads(deleted_path.read_text(encoding="utf-8")) if deleted_path.exists() else []
    for device in access["devices"]:
        device_id = device["family"] + "_1"
        if device_id in deleted or device["family"] not in ("leak", "light", "barrier", "counter", "thermostat"):
            continue
        if str(device.get("apartment_id")) != apartment or not device.get("bound"):
            continue
        bindings.setdefault(device_id, {"serialnumber": str(device["sn"]),
                                       "ext_guid": device["ext"], "signal_map": {}, "seen_tasks": {}})
    path.write_text(json.dumps(bindings, ensure_ascii=False, indent=2), encoding="utf-8")
    env_path = root / "backend" / ".env"
    lines = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.exists() else []
    settings = {"APP_MODE": "live" if live else "local", "UJIN_ACCESS_FILE": json.dumps(access_file.as_posix(), ensure_ascii=False),
                "UJIN_BASE_URL": access["api_base"], "UJIN_APARTMENT_ID": apartment,
                "UJIN_MODEL_CLASS": "integrations_devices", "UJIN_POLL_INTERVAL": "3"}
    lines = [line for line in lines if line.split("=", 1)[0].strip() not in settings]
    env_path.write_text("\n".join([*lines, *(f"{key}={value}" for key, value in settings.items())]) + "\n", encoding="utf-8")
    print(f"Configured {len(bindings)} bindings; mode={'LIVE' if live else 'LOCAL'}. Credentials stay in the access file.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--access-file", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    configure(args.access_file, Path(__file__).resolve().parents[2], args.live)
