"""Человеческие описания типов поверх реальных declarations эмуляторов."""
from __future__ import annotations

from devices import REGISTRY


# Единственное место, где задаётся пользовательское представление сигналов.
# Имена и control/management берутся из Device.declaration(), не копируются сюда.
PRESETS = {
    "light": {
        "title": "Светильник", "icon": "💡", "description": "Свет с управлением яркостью",
        "signals": {
            "lamp": {"title": "Свет", "section": "Управление", "action_title": "Свет", "action_on": "Включить", "action_off": "Выключить"},
            "brightness": {"title": "Яркость", "section": "Управление"},
            "power_w": {"title": "Текущая мощность", "section": "Показания"},
            "energy_kwh": {"title": "Энергопотребление", "section": "Показания"},
            "offline_timeout": {"title": "Автоматическое выключение", "section": "Настройки"},
        },
    },
    "leak": {
        "title": "Датчик протечки", "icon": "💧", "description": "Обнаруживает воду и вскрытие корпуса",
        "signals": {
            "leak": {"title": "Протечка", "section": "Состояния и события", "event_title": "Обнаружена протечка", "event_on": "Обнаружена протечка", "event_off": "Протечки нет"},
            "tamper": {"title": "Вскрытие корпуса", "section": "Состояния и события", "event_title": "Изменилось состояние корпуса"},
            "battery": {"title": "Заряд батареи", "section": "Показания"},
        },
    },
    "thermostat": {
        "title": "Термостат", "icon": "🌡", "description": "Измеряет и поддерживает температуру",
        "signals": {
            "temperature": {"title": "Текущая температура", "section": "Показания"},
            "target_temp": {"title": "Целевая температура", "section": "Управление и настройки"},
            "mode": {"title": "Режим работы", "section": "Управление и настройки"},
            "output": {"title": "Нагрев или охлаждение", "section": "Состояния"},
            "humidity": {"title": "Влажность", "section": "Показания"},
            "fault": {"title": "Состояние датчика", "section": "Состояния"},
        },
    },
    "barrier": {
        "title": "Шлагбаум", "icon": "🚧", "description": "Управляет стрелой и сообщает о препятствиях",
        "signals": {
            "open_cmd": {"title": "Открыть", "section": "Управление", "action_title": "Открыть"},
            "close_cmd": {"title": "Закрыть", "section": "Управление", "action_title": "Закрыть"},
            "hold_time": {"title": "Время удержания открытым", "section": "Настройки"},
            "state": {"title": "Состояние стрелы", "section": "Состояния и события", "event_title": "Изменилось состояние стрелы"},
            "obstacle": {"title": "Препятствие", "section": "Состояния и события", "event_title": "Обнаружено препятствие", "event_on": "Обнаружено препятствие", "event_off": "Препятствий нет"},
            "alarm": {"title": "Авария", "section": "Состояния и события", "event_title": "Состояние аварии", "event_on": "Возникла авария", "event_off": "Аварии нет"},
            "cycles": {"title": "Количество циклов открытия", "section": "Показания"},
        },
    },
    "water_valve": {
        "title": "Клапан воды", "icon": "🚰", "description": "Перекрывает воду и показывает расход и давление",
        "signals": {
            "opened": {"title": "Клапан", "section": "Управление", "action_title": "Клапан воды", "action_on": "Открыть воду", "action_off": "Перекрыть воду"},
            "water_flow": {"title": "Расход воды", "section": "Показания"},
            "pressure": {"title": "Давление", "section": "Показания"},
        },
    },
    "motion_sensor": {
        "title": "Датчик движения", "icon": "🚶", "description": "Сообщает о движении и уровне заряда",
        "signals": {
            "motion": {"title": "Движение", "section": "Состояния и события", "event_title": "Обнаружено движение", "event_on": "Обнаружено движение", "event_off": "Движения нет"},
            "battery": {"title": "Заряд батареи", "section": "Показания"},
        },
    },
    "counter": {
        "title": "Счётчик", "icon": "⚡", "description": "Счётчик электроэнергии с тарифами",
        "signals": {
            "total": {"title": "Общее потребление", "section": "Показания"},
            "kvh_t1": {"title": "Тариф 1", "section": "Показания"},
            "kvh_t2": {"title": "Тариф 2", "section": "Показания"},
            "power_w": {"title": "Текущая мощность", "section": "Показания"},
            "voltage": {"title": "Напряжение", "section": "Показания"},
            "battery": {"title": "Заряд батареи", "section": "Показания"},
            "online": {"title": "Связь", "section": "Состояния"},
            "report_period": {"title": "Период отчёта", "section": "Настройки"},
            "load_relay": {"title": "Реле нагрузки", "section": "Управление", "action_title": "Реле нагрузки", "action_on": "Включить нагрузку", "action_off": "Отключить нагрузку"},
        },
    },
    "elevator": {
        "title": "Лифт", "icon": "🛗", "description": "Показывает этаж и состояние движения, принимает вызовы",
        "signals": {
            "call_requested": {"title": "Вызвать лифт на этаж", "section": "Управление", "action_title": "Вызвать лифт на этаж"},
            "floor_current": {"title": "Текущий этаж", "section": "Состояния"},
            "floor_destination": {"title": "Этаж назначения", "section": "Состояния"},
            "direction": {"title": "Состояние движения", "section": "Состояния"},
            "speed": {"title": "Скорость", "section": "Показания"},
            "door": {"title": "Двери", "section": "Состояния"},
            "floor_changed": {"title": "Этаж изменён", "section": "Состояния и события", "event_title": "Этаж изменён"},
            "emergency": {"title": "Состояние аварии", "section": "Состояния"},
            "emergency_btn": {"title": "Аварийная кнопка", "section": "Управление", "action_title": "Переключить аварийный режим"},
            "floors_total": {"title": "Количество этажей", "section": "Сведения"},
        },
    },
}


def _factory(type_name: str):
    cls = REGISTRY[type_name]
    return cls(serial="preset-preview", logger=lambda _msg: None,
               **({"resource": "electricity"} if type_name == "counter" else {}))


def get_preset(type_name: str) -> dict | None:
    config = PRESETS.get(type_name)
    if not config:
        return None
    declaration = _factory(type_name).declaration()
    declared = {item["name"]: item for item in declaration}
    unknown = set(config["signals"]) - set(declared)
    if unknown:
        raise RuntimeError(f"Preset {type_name} references undeclared signals: {sorted(unknown)}")
    signals = []
    features: dict[str, list[str]] = {}
    for name, meta in config["signals"].items():
        item = {**declared[name], **meta}
        item["section"] = meta["section"]
        if item.get("kind") != "system":
            signals.append(item)
            features.setdefault(meta["section"], []).append(item["title"])
    return {"type": type_name, "title": config["title"], "icon": config["icon"],
            "description": config["description"], "features": features,
            "declaration": signals}


def list_presets() -> list[dict]:
    return [get_preset(type_name) for type_name in PRESETS]
