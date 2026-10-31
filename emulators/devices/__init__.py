"""Набор эмуляторов устройств."""
from .leak_sensor import LeakSensor
from .barrier import Barrier
from .thermostat import Thermostat
from .counter import Counter
from .light import Light
from .water_valve import WaterValve
from .kettle import Kettle
from .curtain import Curtain

REGISTRY = {
    "leak": LeakSensor,
    "barrier": Barrier,
    "thermostat": Thermostat,
    "counter": Counter,
    "light": Light,
    "water_valve": WaterValve,
    "kettle": Kettle,
    "curtain": Curtain,
}
