from __future__ import annotations

import asyncio
import operator
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
                    matched = compare(event.get("value"), trigger.get("operator", "=="),
                                      trigger.get("value", 1))
                    previous = self._trigger_active.get(scenario["id"], False)
                    self._trigger_active[scenario["id"]] = matched
                    if not matched or previous:
                        continue
                    self.log(scenario["id"], f"Событие: {event['device_id']}.{event['signal']} = {event.get('value')}", "trigger")
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
                        for action in actions:
                            await self.manager.command(action["device_id"], action["signal"], action["value"])
                            self.log(scenario["id"], f"{action['device_id']}.{action.get('signal')} ← {action.get('value')}", "action")
                        self.log(scenario["id"], "Сценарий выполнен успешно", "success")
                    except (KeyError, ValueError, PermissionError, TypeError) as exc:
                        self.log(scenario["id"], f"Ошибка действия: {exc}", "error")
        finally:
            self.bus.unsubscribe(queue)
