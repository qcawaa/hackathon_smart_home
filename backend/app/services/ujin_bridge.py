"""Bidirectional bridge. Local FSMs own state; Ujin supplies management tasks.

HTTP runs in worker threads. Successful task IDs are saved before sending the
acknowledgement, so an unavailable platform cannot replay an applied command.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
from collections import defaultdict, deque
from datetime import datetime, timezone

from .ujin_adapter import UjinError


def now():
    return datetime.now(timezone.utc).isoformat()


def signal_rows(info):
    data = info.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("signals"), list):
        raise UjinError("В карточке Ujin отсутствует список сигналов")
    return data["signals"]


def tasks(info):
    """Accept documented raw fields and the BMS task/state projection, including 0."""
    for row in signal_rows(info):
        state = row.get("state") if isinstance(row.get("state"), dict) else {}
        value = next((source[key] for source, key in (
            (row, "signal_task_value"), (row, "task"), (state, "task"))
                      if source.get(key) is not None and source.get(key) != ""), None)
        name = row.get("name") or row.get("signal_name")
        if not name or value is None:
            continue
        stamp = next((source[key] for source, key in (
            (row, "signal_task_dt"), (row, "task_dt"), (state, "task_dt"))
                      if source.get(key) not in (None, "", 0, "0")), None)
        # With a timestamp, a new same-value command is still an actual command.
        if stamp is None and str(value) == str(state.get("value", row.get("value"))):
            continue
        key = json.dumps([str(stamp) if stamp is not None else None, value], sort_keys=True)
        yield name, value, key


def command_value(signal, value):
    if signal.control == "text":
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Команда должна содержать число") from None
    if not math.isfinite(number):
        raise ValueError("Команда должна содержать конечное число")
    # Invert the platform's empty(0) workaround only for discrete signals.
    if number == 0.001 and (signal.control == "switch" or signal.layout):
        number = 0
    if signal.minimum is not None and number < signal.minimum:
        raise ValueError("Значение меньше допустимого")
    if signal.maximum is not None and number > signal.maximum:
        raise ValueError("Значение больше допустимого")
    if signal.control == "switch" and number not in (0, 1):
        raise ValueError("Переключатель принимает 0 или 1")
    if signal.layout and str(int(number) if number.is_integer() else number) not in {str(k) for k in signal.layout}:
        raise ValueError("Значение отсутствует в списке вариантов")
    return int(number) if number.is_integer() else number


def newer_task(key, previous):
    if previous is None:
        return True
    if key == previous:
        return False
    stamp, _ = json.loads(key)
    old_stamp, _ = json.loads(previous)
    if stamp is not None and old_stamp is not None:
        try:
            return float(stamp) > float(old_stamp)
        except (TypeError, ValueError):
            return stamp > old_stamp
    return True


class UjinBridge:
    def __init__(self, manager, storage, bus, adapter):
        self.manager, self.storage, self.bus, self.adapter = manager, storage, bus, adapter
        self.bindings = storage.read("ujin_bindings.json", {})
        self.interval = max(.2, float(os.getenv("UJIN_POLL_INTERVAL", "3")))
        self.connected = None
        self.last_sync = None
        self.logs = deque(maxlen=100)
        self.device_status = {}
        self._pending = defaultdict(deque)
        self._sent = defaultdict(dict)
        self._lock = asyncio.Lock()
        self._workers = []
        self._queue = None

    def status(self):
        result = {**self.adapter.status(), "connected": self.connected,
                  "running": bool(self._workers), "last_sync": self.last_sync,
                  "poll_interval": self.interval, "bindings": self.binding_list(),
                  "logs": list(self.logs)}
        if self.connected:
            result["message"] = "Обмен с Ujin работает" if self._workers else "Ручная синхронизация выполнена"
        elif self.connected is False:
            result["message"] = "Есть ошибки обмена. Повторяем подключение автоматически."
        elif not self.bindings and self.adapter.configured:
            result["message"] = "Привяжите эмуляторы к устройствам Ujin"
        return result

    def binding_list(self):
        return [{"device_id": key, **{k: row[k] for k in ("serialnumber", "ext_guid", "signal_map") if k in row},
                 **self.device_status.get(key, {})} for key, row in self.bindings.items()]

    def save(self):
        self.storage.write("ujin_bindings.json", self.bindings)

    async def log(self, kind, message, device_id=None, **extra):
        row = {"time": now(), "kind": kind, "device_id": device_id,
               "message": self.adapter.safe_message(message), **extra}
        self.logs.appendleft(row)
        await self.bus.publish({"type": "integration", "item": row})

    async def bind(self, device_id, data):
        self.manager.get(device_id)
        if not re.fullmatch(r"[0-9]+", data["serialnumber"]):
            raise ValueError("Серийный номер Ujin должен состоять из цифр")
        if not re.fullmatch(r"[A-Za-z0-9_]+", data["ext_guid"]):
            raise ValueError("Внешний ID: латинские буквы, цифры и подчёркивание")
        if any(key != device_id and row["serialnumber"] == data["serialnumber"]
               for key, row in self.bindings.items()):
            raise ValueError("Устройство Ujin уже связано с другим эмулятором")
        mapping = data.get("signal_map") or {}
        if any(name not in self.manager.get(device_id).signals or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", remote)
               for name, remote in mapping.items()) or len(set(mapping.values())) != len(mapping):
            raise ValueError("Проверьте соответствия сигналов")
        info = await asyncio.to_thread(self.adapter.read_device, data["serialnumber"])
        signal_rows(info)
        remote = info["data"]
        meta = remote.get("meta") or {}
        apartment = (meta.get("apartment") or {}).get("id")
        if apartment is not None and str(apartment) != str(self.adapter.apartment_id):
            raise ValueError("Устройство принадлежит другой квартире")
        ext = remote.get("device_ext_guid") or remote.get("ext_guid")
        if ext and str(ext) != data["ext_guid"]:
            raise ValueError("Внешний ID не совпадает с карточкой Ujin")
        async with self._lock:
            self.bindings[device_id] = {"serialnumber": data["serialnumber"],
                                        "ext_guid": data["ext_guid"], "signal_map": mapping,
                                        "seen_tasks": {}}
            self._sent.pop(device_id, None)
            self._pending.pop(device_id, None)
            self.save()
        await self.log("binding", "Устройство связано с Ujin", device_id)
        return self.binding_list()

    async def unbind(self, device_id):
        async with self._lock:
            self.bindings.pop(device_id, None)
            self._pending.pop(device_id, None)
            self._sent.pop(device_id, None)
            self.device_status.pop(device_id, None)
            self.save()
        return {"ok": True}

    def remote_name(self, binding, name):
        return binding.get("signal_map", {}).get(name, self.adapter.model_class + "_" + name)

    async def _receive(self, device_id, binding, info):
        dev = self.manager.get(device_id)
        inverse = {self.remote_name(binding, name): name for name in dev.signals}
        inverse.update({name: name for name in dev.signals if name not in binding.get("signal_map", {})})
        seen = binding.setdefault("seen_tasks", {})
        for remote, value, key in tasks(info):
            if not newer_task(key, seen.get(remote)):
                continue
            name = inverse.get(remote)
            if name is None or not dev.signals[name].writable:
                continue
            converted = command_value(dev.signals[name], value)
            await self.manager.command(device_id, name, converted)
            seen[remote] = key  # Save only after the FSM has successfully applied it.
            self.save()
            self._pending[device_id].append((name, dev.signals[name].value))
            await self.log("command", f"Получена и выполнена команда: {dev.signals[name].title}",
                           device_id, signal=name, value=converted)

    @staticmethod
    def wire(value):
        if isinstance(value, (int, float)) and math.isfinite(value):
            return 0.001 if value == 0 else value
        return None

    async def _publish_batch(self, device_id, binding, batch, known):
        rows, new = [], []
        prefix = self.adapter.model_class + "_"
        for name, value in batch:
            wire = self.wire(value)
            if wire is None:
                continue  # Float-signal transport; unsupported signals are listed in status.
            remote = self.remote_name(binding, name)
            short = remote.removeprefix(prefix)
            if remote not in known and short in known:
                remote = short
            row = {"sn": binding["ext_guid"], "s": remote, "v": wire, "c": self.adapter.model_class}
            rows.append(row)
            if remote not in known:
                if not remote.startswith(prefix):
                    raise ValueError("Новый сигнал должен использовать префикс класса Ujin")
                new.append({**row, "s": remote[len(prefix):]})
        if rows:
            await asyncio.to_thread(self.adapter.publish, rows, new_short=new, serialnumber=binding["serialnumber"])
            # The UAE endpoint can return error=0 while silently dropping data.
            # Confirm values via a separate read before accepting the delivery.
            info = await asyncio.to_thread(self.adapter.read_device, binding["serialnumber"])
            actual = {s.get("name") or s.get("signal_name"): (s.get("state") or {}).get("value", s.get("value"))
                      for s in signal_rows(info)}
            missing = []
            for row in rows:
                value = actual.get(row["s"], actual.get(row["s"].removeprefix(prefix)))
                try:
                    matched = math.isclose(float(value), float(row["v"]), rel_tol=1e-6, abs_tol=1e-8)
                except (TypeError, ValueError):
                    matched = False
                if not matched:
                    missing.append(row["s"])
            if missing:
                raise UjinError("Ujin не подтвердил показания: " + ", ".join(missing) +
                                ". Проверьте внешний ID, словари сигналов и их видимость в BMS.")
            known.update(row["s"] for row in rows)
            self._sent[device_id].update(batch)
            self.device_status[device_id]["last_publish"] = now()
            await self.log("publish", f"Отправлено сигналов: {len(rows)}", device_id)

    async def _sync_device(self, device_id, binding):
        dev = self.manager.get(device_id)
        self.device_status.setdefault(device_id, {})
        info = await asyncio.to_thread(self.adapter.read_device, binding["serialnumber"])
        signals = signal_rows(info)
        known = {s.get("name") or s.get("signal_name") for s in signals}
        readonly = {s.get("name") or s.get("signal_name") for s in signals
                    if s.get("management", s.get("signal_management")) == "r"
                    or (s.get("state") or {}).get("readonly") is True}
        self.device_status[device_id]["readonly_commands"] = [name for name, sig in dev.signals.items()
            if sig.writable and (self.remote_name(binding, name) in readonly or name in readonly)]
        self.device_status[device_id]["unsupported_signals"] = [name for name, sig in dev.signals.items()
            if sig.kind != "system" and sig.publishable and self.wire(sig.value) is None]
        await self._receive(device_id, binding, info)
        pending = self._pending[device_id]
        # Preserve consecutive transitions of one signal (e.g. wet -> dry).
        for _ in range(100):
            if not pending:
                break
            batch = []
            names = set()
            for name, value in pending:
                if name in names:
                    break
                batch.append((name, value))
                names.add(name)
            await self._publish_batch(device_id, binding, batch, known)
            for _ in batch:
                pending.popleft()
        snapshot = [(name, sig.value) for name, sig in dev.signals.items()
                    if sig.kind != "system" and sig.publishable
                    and self._sent[device_id].get(name) != sig.value]
        if snapshot and not pending:
            await self._publish_batch(device_id, binding, snapshot, known)
        self.device_status[device_id].update(connected=True, last_poll=now(), error=None)

    async def sync_once(self):
        if not self.adapter.configured:
            raise UjinError("Для LIVE настройте доступы в backend/.env")
        async with self._lock:
            ok = True
            active = 0
            for device_id, binding in tuple(self.bindings.items()):
                if device_id not in self.manager.devices:
                    continue
                active += 1
                try:
                    await self._sync_device(device_id, binding)
                except (UjinError, OSError, ValueError, TypeError, KeyError) as exc:
                    ok = False
                    message = self.adapter.safe_message(exc)
                    self.device_status.setdefault(device_id, {}).update(connected=False, error=message)
                    await self.log("error", message, device_id)
            self.connected = ok if active else None
            self.last_sync = now()
        result = self.status()
        await self.bus.publish({"type": "integration_status", "status": result})
        return result

    async def _listen(self):
        while True:
            event = await self._queue.get()
            device_id, name = event.get("device_id"), event.get("signal")
            if event.get("type") != "signal" or device_id not in self.bindings:
                continue
            dev = self.manager.devices.get(device_id)
            sig = dev.signals.get(name) if dev else None
            # Measurements are sent from the latest snapshot; keep every discrete
            # transition without building an unbounded queue of periodic meters.
            if (sig and sig.publishable and sig.kind != "system"
                    and (sig.control in ("switch", "list", "push_time", "button") or sig.layout)):
                self._pending[device_id].append((name, event["value"]))

    async def _run(self):
        failures = 0
        while True:
            await self.sync_once()
            failures = min(failures + 1, 4) if self.connected is False else 0
            await asyncio.sleep(min(60, self.interval * 2 ** failures))

    def start(self):
        if self.adapter.enabled and self.adapter.configured and not self._workers:
            self._queue = self.bus.subscribe()
            self._workers = [asyncio.create_task(self._listen()), asyncio.create_task(self._run())]

    async def stop(self):
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        if self._queue is not None:
            self.bus.unsubscribe(self._queue)
            self._queue = None
