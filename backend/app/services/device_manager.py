from __future__ import annotations

import asyncio
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EMU = ROOT / "emulators"
if str(EMU) not in sys.path:
    sys.path.insert(0, str(EMU))
from devices import REGISTRY  # noqa: E402
from .generic_device import GenericDevice
from .device_presets import PRESETS, get_preset


class DeviceManager:
    def __init__(self, storage, bus):
        self.storage, self.bus = storage, bus
        self.devices = {}
        self.tick_task = None
        self._old = {}
        self.user_devices = {}
        self.device_types = {}
        self.seed_devices = set()
        self._seed()

    def _seed(self):
        deleted = set(self.storage.read("deleted_devices.json", []))
        for device_id, family in (("leak_1", "leak"), ("light_1", "light"),
                                  ("thermostat_1", "thermostat"), ("barrier_1", "barrier"),
                                  ("counter_1", "counter"), ("kettle_1", "kettle"),
                                  ("curtain_1", "curtain")):
            if device_id in deleted:
                continue
            device = REGISTRY[family](serial=device_id, logger=lambda _msg: None)
            self.devices[device_id] = device
            self.device_types[device_id] = family
            self.seed_devices.add(device_id)
        for row in self.storage.read("generic_devices.json", []):
            self._add_generic(row)
        for row in self.storage.read("preset_devices.json", []):
            if row.get("type") in PRESETS and row.get("id") not in self.devices:
                self._add_preset(row)
        self._snapshot_all()

    def _add_preset(self, row):
        device_type = row["type"]
        kwargs = {"resource": "electricity"} if device_type == "counter" else {}
        device = REGISTRY[device_type](serial=row["id"], logger=lambda _msg: None, **kwargs)
        device.title = row["title"]
        self.devices[row["id"]] = device
        self.device_types[row["id"]] = device_type
        self.user_devices[row["id"]] = {"type": device_type, "title": row["title"]}

    def _add_generic(self, row):
        device_id = row["id"]
        self.devices[device_id] = GenericDevice(device_id, row["title"], row["signals"])
        self._old[device_id] = self.get_state(device_id)

    def _snapshot_all(self):
        self._old = {key: self.get_state(key) for key in self.devices}

    def get(self, device_id):
        if device_id not in self.devices:
            raise KeyError(device_id)
        return self.devices[device_id]

    def get_state(self, device_id):
        dev = self.get(device_id)
        return {name: sig.value for name, sig in dev.signals.items()}

    def details(self, device_id):
        dev = self.get(device_id)
        row = {"id": device_id, "title": dev.title, "model": dev.model,
               "state": self.get_state(device_id), "declaration": dev.declaration(),
               "source": "LOCAL"}
        if isinstance(dev, GenericDevice):
            row["user_created"] = True
            row["deletable"] = True
        if device_id in self.device_types:
            preset = get_preset(self.device_types[device_id])
            row.update({"type": preset["type"], "preset_title": preset["title"],
                        "icon": preset["icon"], "user_created": device_id in self.user_devices,
                        "deletable": device_id in self.user_devices or device_id in self.seed_devices})
            presentation = {signal["name"]: signal for signal in preset["declaration"]}
            row["declaration"] = [
                {**signal, **{k: v for k, v in presentation.get(signal["name"], {}).items()
                              if k not in ("name", "control", "management", "kind", "group", "min", "max", "layout", "measure")}}
                for signal in row["declaration"]
                if signal["name"] in presentation
            ]
        return row

    def list(self):
        return [self.details(device_id) for device_id in self.devices]

    def create_preset(self, device_type, title):
        if device_type not in PRESETS:
            raise ValueError("Неизвестный тип устройства")
        device_id = f"{device_type}_{uuid.uuid4().hex[:8]}"
        row = {"id": device_id, "type": device_type, "title": title}
        rows = self.storage.read("preset_devices.json", [])
        rows.append(row)
        self.storage.write("preset_devices.json", rows)
        self._add_preset(row)
        self._old[device_id] = self.get_state(device_id)
        return self.details(device_id)

    def update_preset(self, device_id, title):
        if device_id not in self.user_devices:
            raise KeyError(device_id)
        self.devices[device_id].title = title
        self.user_devices[device_id]["title"] = title
        rows = self.storage.read("preset_devices.json", [])
        for row in rows:
            if row["id"] == device_id:
                row["title"] = title
        self.storage.write("preset_devices.json", rows)
        return self.details(device_id)

    def remove_preset(self, device_id):
        if device_id not in self.user_devices:
            raise KeyError(device_id)
        self.devices.pop(device_id)
        self._old.pop(device_id, None)
        self.device_types.pop(device_id, None)
        self.user_devices.pop(device_id, None)
        rows = [row for row in self.storage.read("preset_devices.json", []) if row["id"] != device_id]
        self.storage.write("preset_devices.json", rows)

    def remove_device(self, device_id):
        if device_id in self.user_devices:
            self.remove_preset(device_id)
            return
        if device_id in self.devices and isinstance(self.devices[device_id], GenericDevice):
            self.remove_generic(device_id)
            return
        if device_id in self.seed_devices:
            self.devices.pop(device_id)
            self._old.pop(device_id, None)
            self.device_types.pop(device_id, None)
            self.seed_devices.remove(device_id)
            deleted = self.storage.read("deleted_devices.json", [])
            if device_id not in deleted:
                deleted.append(device_id)
            self.storage.write("deleted_devices.json", deleted)
            return
        raise KeyError(device_id)

    async def command(self, device_id, signal_name, value):
        dev = self.get(device_id)
        sig = dev.signals.get(signal_name)
        if sig is None:
            raise ValueError("Сигнал не найден")
        if not sig.writable:
            raise PermissionError("Сигнал доступен только для чтения")
        old = self.get_state(device_id)
        dev.set_value(signal_name, value)
        command_result = dev.on_command(signal_name, value)
        dev.step(0)
        await self._publish_diff(device_id, old)
        result = self.details(device_id)
        if command_result:
            result["command_result"] = command_result
        return result

    async def simulate(self, device_id, signal_name, value):
        dev = self.get(device_id)
        old = self.get_state(device_id)
        if signal_name == "leak" and hasattr(dev, "set_wet"):
            dev.set_wet(bool(value))
            dev.step(0)
        elif signal_name in dev.signals and dev.signals[signal_name].management == "r":
            dev.set_value(signal_name, value)
        else:
            raise ValueError("Эту величину нельзя эмулировать")
        await self._publish_diff(device_id, old)
        return self.details(device_id)

    async def _publish_diff(self, device_id, old):
        state = self.get_state(device_id)
        self._old[device_id] = state
        for signal, value in state.items():
            if old.get(signal) != value:
                event = {"type": "signal", "device_id": device_id, "signal": signal,
                         "value": value, "state": state}
                await self.bus.publish(event)
                await self.bus.publish({"type": "device_state", "device_id": device_id,
                                        "state": state, "changed_signal": signal})

    async def _tick_loop(self):
        while True:
            await asyncio.sleep(1)
            for device_id, dev in tuple(self.devices.items()):
                old = self.get_state(device_id)
                try:
                    dev.step(1)
                    await self._publish_diff(device_id, old)
                except Exception as exc:
                    await self.bus.publish({"type": "error", "message": str(exc)})

    def start(self):
        self.tick_task = asyncio.create_task(self._tick_loop())

    async def stop(self):
        if self.tick_task:
            self.tick_task.cancel()
            try:
                await self.tick_task
            except asyncio.CancelledError:
                pass

    def create_generic(self, data):
        rows = self.storage.read("generic_devices.json", [])
        device_id = data.get("id") or f"device_{uuid.uuid4().hex[:8]}"
        if not device_id or device_id in self.devices:
            raise ValueError("Устройство с таким идентификатором уже существует")
        for sig in data["signals"]:
            if (not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,39}", sig["name"])
                    or sig["name"] == "fw"):
                raise ValueError("Имя сигнала: латинские буквы, цифры и подчёркивание")
            if sig.get("management", "r") not in ("r", "rw", "w"):
                raise ValueError("Неизвестный режим управления сигналом")
        row = {"id": device_id, "title": data["title"], "signals": data["signals"]}
        rows.append(row)
        self.storage.write("generic_devices.json", rows)
        self._add_generic(row)
        return self.details(device_id)

    def remove_generic(self, device_id):
        if device_id not in self.devices or not isinstance(self.devices[device_id], GenericDevice):
            raise KeyError(device_id)
        self.devices.pop(device_id)
        self._old.pop(device_id, None)
        rows = [row for row in self.storage.read("generic_devices.json", []) if row["id"] != device_id]
        self.storage.write("generic_devices.json", rows)

    def rename_generic(self, device_id, title):
        if device_id not in self.devices or not isinstance(self.devices[device_id], GenericDevice):
            raise KeyError(device_id)
        rows = self.storage.read("generic_devices.json", [])
        found = False
        for row in rows:
            if row["id"] == device_id:
                row["title"] = title
                found = True
        if not found:
            raise KeyError(device_id)
        self.storage.write("generic_devices.json", rows)
        self.devices[device_id].title = title
        return self.details(device_id)

    def update_generic(self, device_id, data):
        if device_id not in self.devices or not isinstance(self.devices[device_id], GenericDevice):
            raise KeyError(device_id)
        for sig in data["signals"]:
            if (not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,39}", sig["name"])
                    or sig["name"] == "fw"):
                raise ValueError("Имя сигнала: латинские буквы, цифры и подчёркивание")
            if sig.get("management", "r") not in ("r", "rw", "w"):
                raise ValueError("Неизвестный режим управления сигналом")
        row = {"id": device_id, "title": data["title"], "signals": data["signals"]}
        rows = self.storage.read("generic_devices.json", [])
        rows = [row if item["id"] == device_id else item for item in rows]
        self.storage.write("generic_devices.json", rows)
        self.devices.pop(device_id)
        self._add_generic(row)
        return self.details(device_id)

