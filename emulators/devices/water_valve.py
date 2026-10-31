"""Эмулятор клапана с подтверждением положения после команды."""
from core import Device, Signal


class WaterValve(Device):
    model = "emul_water_valve"
    title = "Клапан воды"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_signal(Signal("opened", "Клапан открыт", "switch", "rw", "capability", 1,
                               layout={0: "закрыт", 1: "открыт"}))

    def on_command(self, name, value):
        if name == "opened":
            self.set_value(name, int(float(value) != 0))

    def tick(self, dt):
        pass
