"""Шлагбаум: открытие по команде на фиксированные 120 секунд."""
from core import Device, Signal

CLOSED, OPEN = 0, 2
OPEN_SECONDS = 120
LAYOUT = {CLOSED: "закрыто", OPEN: "открыто"}


class Barrier(Device):
    model = "emul_barrier"
    title = "Шлагбаум"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._open_left = 0
        self.add_signal(Signal("open_cmd", "Открыть на 120 секунд", "push_time", "w",
                               "capability", 0))
        self.add_signal(Signal("state", "Состояние стрелы", "list", "r", "property",
                               CLOSED, layout=LAYOUT))

    def on_command(self, name, value):
        if name == "open_cmd":
            self.set_value("open_cmd", 0)
            if value == 1 and self.signals["state"].value == CLOSED:
                self._open_left = OPEN_SECONDS
                self.set_value("state", OPEN)

    def tick(self, dt):
        if self._open_left > 0:
            self._open_left = max(0, self._open_left - dt)
            if self._open_left == 0:
                self.set_value("state", CLOSED)
