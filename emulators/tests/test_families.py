import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import Signal  # noqa: E402
from devices.counter import Counter  # noqa: E402
from devices.light import Light  # noqa: E402


class TestSignalGroups(unittest.TestCase):
    def test_group_mapping(self):
        self.assertEqual(Signal("a", "A", "graph", "r", "property").group, "property")
        self.assertEqual(Signal("b", "B", "switch", "rw", "capability").group, "capability")
        self.assertEqual(Signal("c", "C", "counter", "rw", "setting").group, "setting")
        self.assertEqual(Signal("d", "D", "button", "w", "capability").group, "capability")


class TestCounter(unittest.TestCase):
    def test_energy_grows(self):
        c = Counter(serial="1", resource="electricity")
        v0 = c.signals["total"].value
        for _ in range(5):
            c.tick(1)
        self.assertGreater(c.signals["total"].value, v0)

    def test_relay_off_stops_power(self):
        c = Counter(serial="1")
        c.signals["load_relay"].value = 0
        c.tick(1)
        self.assertEqual(c.signals["power_w"].value, 0.0)

    def test_water_resource(self):
        c = Counter(serial="1", resource="hot")
        for _ in range(3):
            c.tick(1)
        self.assertGreater(c.signals["total"].value, 1000.0)
        self.assertIn("flow", c.signals)


class TestLight(unittest.TestCase):
    def test_on_measures_power(self):
        l = Light(serial="1")
        l.signals["lamp"].value = 1
        l.tick(1)
        self.assertGreater(l.signals["power_w"].value, 0)
        self.assertGreater(l.signals["energy_kwh"].value, 0)

    def test_timer_turns_off(self):
        l = Light(serial="1")
        l.on_command("lamp", 1)
        l.signals["offline_timeout"].value = 2
        l.on_command("lamp", 1)
        for _ in range(3):
            l.tick(1)
        self.assertEqual(l.signals["lamp"].value, 0)


if __name__ == "__main__":
    unittest.main()
