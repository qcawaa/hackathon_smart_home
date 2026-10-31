def compile_autoscript(scenario: dict, bindings=None, model_class="integrations_devices") -> dict:
    """Compile the native event/action subset to the starter pack wire format."""
    trigger = scenario["trigger"]
    actions = scenario.get("actions") or [scenario.get("action") or {}]
    if (trigger.get("operator", "==") not in ("==", "eq") or scenario.get("condition")
            or scenario.get("conditions") or len(actions) != 1):
        raise ValueError("Ujin Autoscripts поддерживает только простое равенство без отдельного условия")
    action = actions[0]

    def address(part):
        binding = (bindings or {}).get(part["device_id"])
        if not binding:
            raise ValueError("Сначала привяжите все устройства сценария к Ujin")
        name = binding.get("signal_map", {}).get(part["signal"], part["signal"]).removeprefix(model_class + "_")
        return f"device-{binding['serialnumber']}:{name}"

    return {
        "title": scenario["title"],
        "when": f"when:{address(trigger)}={trigger.get('value', 1)}",
        "then": f"{address(action)}:{action['value']}",
    }
