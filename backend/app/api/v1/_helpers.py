from __future__ import annotations


def scenario_rows(storage):
    return storage.read("scenarios.json", [])


def scenarios_using_device(device_id, storage):
    affected = []
    for scenario in scenario_rows(storage):
        parts = [scenario.get("trigger", {})]
        parts.extend(scenario.get("conditions", []))
        if scenario.get("condition"):
            parts.append(scenario["condition"])
        parts.extend(scenario.get("actions", []))
        if scenario.get("action"):
            parts.append(scenario["action"])
        if any(part.get("device_id") == device_id for part in parts):
            affected.append(scenario)
    return affected


def validate_scenario(data, manager):
    trigger = data.get("trigger", {})
    actions = data.get("actions") or [data.get("action") or {}]
    if not actions:
        raise ValueError("Добавьте хотя бы одно действие")
    for part, writable in [(trigger, False), *[(action, True) for action in actions]]:
        dev = manager.devices.get(part.get("device_id", ""))
        if not dev or part.get("signal") not in dev.signals:
            raise ValueError("Устройство или сигнал сценария не найдены")
        if writable and not dev.signals[part["signal"]].writable:
            raise ValueError("Действие должно управлять writable-сигналом")
    conditions = data.get("conditions", [])
    if data.get("condition"):
        conditions = [data["condition"], *conditions]
    for condition in conditions:
        dev = manager.devices.get(condition.get("device_id", ""))
        if not dev or condition.get("signal") not in dev.signals:
            raise ValueError("Сигнал условия не найден")
        if condition.get("operator", "==") not in ("==", "eq", "!=", ">", "<", ">=", "<="):
            raise ValueError("Неизвестный оператор условия")
    if trigger.get("operator", "==") not in ("==", "eq", "!=", ">", "<", ">=", "<="):
        raise ValueError("Неизвестный оператор условия")