from __future__ import annotations

import asyncio
import operator
import uuid
from datetime import datetime, timezone


OPS = {"==": operator.eq, "eq": operator.eq, "!=": operator.ne, ">": operator.gt,
       "<": operator.lt, ">=": operator.ge, "<=": operator.le}


def compare(actual, op: str, expected) -> bool:
    if op not in OPS:
        return False
    try:
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return OPS[op](actual, expected)
        if op in (">", "<", ">=", "<="):
            return OPS[op](float(actual), float(expected))
        return OPS[op](str(actual), str(expected))
    except (TypeError, ValueError):
        return False


class ScenarioEngine:
    def __init__(self, manager, storage, bus):
        self.manager, self.storage, self.bus = manager, storage, bus
        self.logs: list[dict] = []
        self.task: asyncio.Task | None = None
        self._trigger_active: dict[str, bool] = {}

    def start(self):
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def log(self, scenario, message, node=""):
        row = {"time": datetime.now(timezone.utc).isoformat(), "scenario_id": scenario,
               "message": message, "node_id": node}
        self.logs.insert(0, row)
        del self.logs[100:]
        asyncio.create_task(self.bus.publish({"type": "execution", "item": row}))

    def describe_signal(self, device_id, signal_name, value):
        """Build a readable log label without exposing protocol identifiers."""
        try:
            device = self.manager.get(device_id)
            signal = device.signals[signal_name]
        except KeyError:
            return "Параметр устройства"
        if signal.control == "switch":
            try:
                enabled = float(value) != 0
            except (TypeError, ValueError):
                enabled = bool(value)
            shown = "Вкл" if enabled else "Выкл"
        elif signal.control in ("push_time", "button"):
            shown = "Выполнено"
        elif signal.layout:
            shown = signal.layout.get(value, signal.layout.get(str(value), value))
            if "протеч" in signal.title.lower():
                shown = "Обнаружена" if str(value) == "1" else "Не обнаружена"
            else:
                shown = str(shown)
                shown = shown[:1].upper() + shown[1:]
        else:
            shown = value
        suffix = f" {signal.measure}" if signal.measure and signal.control not in ("push_time", "button") else ""
        return f"{device.title} · {signal.title}: {shown}{suffix}"

    async def execute_action(self, scenario_id, device_id, signal_name, value):
        """Выполнить действие и сообщить интерфейсу его фактический результат."""
        device = self.manager.get(device_id)
        try:
            response = await self.manager.command(device_id, signal_name, value)
        except (KeyError, ValueError, PermissionError, TypeError) as exc:
            await self.bus.publish({"type": "scenario_action", "id": uuid.uuid4().hex,
                                    "scenario_id": scenario_id, "device_id": device_id,
                                    "status": "error", "message": f"{device.title} → {exc}"})
            raise
        signal = device.signals[signal_name]
        actual = response["state"][signal_name]
        blocked = (device.model == "emul_kettle" and signal_name == "on"
                   and bool(float(value)) and not actual)
        if blocked:
            shown = response.get("command_result") or "Не включён"
        elif signal.control == "switch":
            shown = "Вкл" if float(actual) else "Выкл"
        elif signal.control in ("push_time", "button"):
            state_name = "opened" if device.model == "emul_curtain" else "state"
            state_signal = device.signals.get(state_name)
            state = response["state"].get(state_name)
            shown = (state_signal.layout or {}).get(state) if state_signal else None
            shown = shown or response.get("command_result") or signal.title
        else:
            shown = (signal.layout or {}).get(actual, actual)
            if signal.measure:
                shown = f"{shown} {signal.measure}"
        shown = str(shown)
        shown = shown[:1].upper() + shown[1:]
        label = device.title
        if signal.control not in ("switch", "push_time", "button"):
            label += f" · {signal.title}"
        notice = {"type": "scenario_action", "id": uuid.uuid4().hex,
                  "scenario_id": scenario_id, "device_id": device_id, "signal": signal_name,
                  "value": actual, "status": "warning" if blocked else "success",
                  "message": f"{label} → {shown}"}
        await self.bus.publish(notice)
        response["scenario_action"] = notice
        return response

    async def _run(self):
        queue = self.bus.subscribe()
        try:
            while True:
                event = await queue.get()
                if event.get("type") != "signal":
                    continue
                for scenario in self.storage.read("scenarios.json", []):
                    if not scenario.get("enabled"):
                        continue
                    trigger = scenario.get("trigger", {})
                    if (trigger.get("device_id") != event.get("device_id") or
                            trigger.get("signal") != event.get("signal")):
                        continue
                    try:
                        trigger_signal = self.manager.get(event["device_id"]).signals[event["signal"]]
                    except KeyError:
                        continue
                    event_signal = trigger_signal.control in ("push_time", "button") and trigger_signal.management == "r"
                    matched = event_signal or compare(event.get("value"), trigger.get("operator", "=="),
                                                      trigger.get("value", 1))
                    previous = self._trigger_active.get(scenario["id"], False)
                    self._trigger_active[scenario["id"]] = False if event_signal else matched
                    if not matched or (previous and not event_signal):
                        continue
                    self.log(scenario["id"], f"Событие: {self.describe_signal(event['device_id'], event['signal'], event.get('value'))}", "trigger")
                    conditions = scenario.get("conditions", [])
                    if scenario.get("condition"):
                        conditions = [scenario["condition"], *conditions]
                    passed = True
                    for condition in conditions:
                        try:
                            state = self.manager.get_state(condition["device_id"])
                        except KeyError:
                            self.log(scenario["id"], "Устройство условия недоступно", "condition_failed")
                            passed = False
                            break
                        if not compare(state.get(condition["signal"]), condition.get("operator", "=="),
                                       condition.get("value")):
                            self.log(scenario["id"], "Условие не выполнено", "condition_failed")
                            passed = False
                            break
                        self.log(scenario["id"], "Условие выполнено", "condition_passed")
                    if not passed:
                        continue
                    actions = scenario.get("actions") or [scenario.get("action", {})]
                    try:
                        partial = False
                        for action in actions:
                            result = await self.execute_action(scenario["id"], action["device_id"], action["signal"], action["value"])
                            notice = result["scenario_action"]
                            partial = partial or notice["status"] != "success"
                            self.log(scenario["id"], notice["message"], "action")
                        self.log(scenario["id"], "Сценарий выполнен частично" if partial else "Сценарий выполнен успешно", "error" if partial else "success")
                    except (KeyError, ValueError, PermissionError, TypeError) as exc:
                        self.log(scenario["id"], f"Ошибка действия: {exc}", "error")
        finally:
            self.bus.unsubscribe(queue)
