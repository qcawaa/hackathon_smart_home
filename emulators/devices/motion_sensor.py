"""Эмулятор датчика движения для существующего каталога приложения."""
from core import Device, Signal


class MotionSensor(Device):
    model = "emul_motion_sensor"
    title = "Датчик движения"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.motion = False
        self.add_signal(Signal("motion", "Движение", "switch", "r", "property", 0))

    def set_motion(self, value):
        self.motion = bool(value)

    def tick(self, dt):
        self.set_value("motion", int(self.motion))
