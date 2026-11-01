"""Постоянные сценарии ручного запуска для всех устройств подходящего типа."""

QUICK_SCENARIOS = {
    "quick_home": {"id": "quick_home", "title": "Я дома", "pinned": True, "deletable": False},
    "quick_good_night": {"id": "quick_good_night", "title": "Спокойной ночи!", "pinned": True, "deletable": False},
}


async def run_quick_scenario(scenario_id, manager, engine):
    preset = QUICK_SCENARIOS[scenario_id]
    commands = ({"light": ("lamp", 1), "kettle": ("on", 1)} if scenario_id == "quick_home"
                else {"light": ("lamp", 0), "curtain": ("close_cmd", 1)})
    results = []
    for device_id, device_type in list(manager.device_types.items()):
        if device_type not in commands:
            continue
        signal, value = commands[device_type]
        title = manager.get(device_id).title
        try:
            response = await engine.execute_action(scenario_id, device_id, signal, value)
            blocked = device_type == "kettle" and response["state"]["on"] != 1
            message = response.get("command_result") or (
                "Чайник не включён" if blocked else f"{title}: команда выполнена")
            result = {"device_id": device_id, "title": title,
                      "status": "blocked" if blocked else "completed", "message": message,
                      "notification": response["scenario_action"]}
        except (KeyError, ValueError, PermissionError, TypeError) as exc:
            result = {"device_id": device_id, "title": title, "status": "error", "message": str(exc)}
        results.append(result)
        engine.log(scenario_id, result["message"], "success" if result["status"] == "completed" else "error")
    status = ("empty" if not results else "partial" if any(row["status"] != "completed" for row in results)
              else "completed")
    engine.log(scenario_id, f'«{preset["title"]}»: ' + {
        "empty": "нет подходящих устройств", "partial": "выполнено частично",
        "completed": "сценарий выполнен"}[status], "success" if status == "completed" else "error")
    return {"id": scenario_id, "title": preset["title"], "status": status, "results": results}
