"""Умный чайник: защита от недостатка воды, нагрев и автоотключение."""
import math

from core import Device, Signal

MIN_WATER_ML = 300


class Kettle(Device):
    model = "emul_kettle"
    title = "Умный чайник"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._water_ml = 500
        self.add_signal(Signal("on", "Нагрев", "switch", "rw", "capability", 0))
        self.add_signal(Signal("water_ml", "Объём воды (эмуляция)", "number", "rw",
                               "setting", self._water_ml, "мл", 0, 2000))
        self.add_signal(Signal("temperature", "Температура воды", "graph", "r",
                               "property", 20.0, "°C"))
        self.add_signal(Signal("low_water", "Недостаточно воды", "list", "r",
                               "property", 0, layout={0: "нет", 1: "меньше 300 мл"}))

    def _check_water(self):
        low = self._water_ml < MIN_WATER_ML
        self.set_value("low_water", int(low))
        if low:
            self.set_value("on", 0)
        return low

    def on_command(self, name, value):
        if name == "water_ml":
            try:
                amount = float(value)
                if not math.isfinite(amount) or not 0 <= amount <= 2000:
                    raise ValueError
            except (TypeError, ValueError):
                self.set_value("water_ml", self._water_ml)
                raise ValueError("Объём воды должен быть от 0 до 2000 мл")
            self._water_ml = amount
            self.set_value("water_ml", amount)
            self._check_water()
        elif name == "on":
            enabled = int(float(value) != 0)
            self.set_value("on", enabled)
            if self._check_water() and enabled:
                return "Чайник не включён: налейте не менее 300 мл воды."

    def tick(self, dt):
        self._check_water()
        temperature = self.signals["temperature"].value
        if self.signals["on"].value:
            temperature = min(100.0, temperature + 5 * dt)
            if temperature >= 100:
                self.set_value("on", 0)
        else:
            temperature = max(20.0, temperature - 0.5 * dt)
        self.set_value("temperature", round(temperature, 1))
