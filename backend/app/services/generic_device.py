from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EMU = ROOT / "emulators"
if str(EMU) not in sys.path:
    sys.path.insert(0, str(EMU))
from core import Device, Signal  # noqa: E402


class GenericDevice(Device):
    model = "generic_device"

    def __init__(self, serial: str, title: str, signals: list[dict[str, Any]], logger=None):
        self.title = title
        super().__init__(serial=serial, logger=logger or (lambda _msg: None))
        for row in signals:
            self.add_signal(Signal(
                name=row["name"], title=row.get("title", row["name"]),
                control=row.get("control", "text"),
                management=row.get("management", "r"),
                kind=row.get("kind", "property"), value=row.get("value", 0),
                measure=row.get("measure", ""), minimum=row.get("min"),
                maximum=row.get("max"), layout=row.get("layout"),
                zero_safe=bool(row.get("zero_safe", False)),
            ))

    def tick(self, dt: int) -> None:
        return

    def on_command(self, name: str, value: Any) -> None:
        signal = self.signals[name]
        if signal.control in ("range", "counter", "number"):
            value = float(value) if "." in str(value) else int(value)
        self.set_value(name, self.clamp(name, value))
