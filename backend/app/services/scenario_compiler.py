def compile_autoscript(scenario: dict) -> dict:
    """Compile the native event/action subset to the starter pack wire format."""
    trigger = scenario["trigger"]
    action = scenario.get("action") or (scenario.get("actions") or [{}])[0]
    if trigger.get("operator") != "==" or scenario.get("condition"):
        raise ValueError("Ujin Autoscripts поддерживает только простое равенство без отдельного условия")
    return {
        "title": scenario["title"],
        "when": f"when:device-{trigger['device_id']}:{trigger['signal']}={trigger.get('value', 1)}",
        "then": f"device-{action['device_id']}:{action['signal']}:{action['value']}",
    }
