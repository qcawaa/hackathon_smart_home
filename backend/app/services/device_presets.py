"""Каталог из деклараций эмуляторов: один источник возможностей устройств."""
from devices import REGISTRY


def _preset(name, factory):
    device = factory(serial="preview", logger=lambda _: None)
    declaration = [s for s in device.declaration() if s["kind"] != "system"
                   and not (name == "leak" and s["name"] == "self_test")]
    labels = {"property": "Свойства", "capability": "Возможности", "setting": "Настройки"}
    return {"type": name, "title": device.title, "icon": name,
            "description": f"Эмулятор: {device.title.lower()}", "declaration": declaration,
            "features": {label: [s["title"] for s in declaration if s["group"] == group]
                         for group, label in labels.items()}}


PRESETS = {name: _preset(name, factory) for name, factory in REGISTRY.items()}


def get_preset(name):
    return PRESETS.get(name)


def list_presets():
    return list(PRESETS.values())
