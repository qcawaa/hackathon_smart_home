"""Умная гардина: открытие и закрытие штор по команде."""
from core import Device, Signal


class Curtain(Device):
    model = "emul_curtain"
    title = "Умная гардина"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_signal(Signal("open_cmd", "Открыть шторы", "push_time", "w", "capability", 0))
        self.add_signal(Signal("close_cmd", "Закрыть шторы", "push_time", "w", "capability", 0))
        self.add_signal(Signal("opened", "Положение штор", "list", "r", "property", 0,
                               layout={0: "закрыты", 1: "открыты"}))

    def on_command(self, name, value):
        if name in ("open_cmd", "close_cmd"):
            self.set_value(name, 0)
            if value == 1:
                self.set_value("opened", int(name == "open_cmd"))

    def tick(self, dt):
        pass
