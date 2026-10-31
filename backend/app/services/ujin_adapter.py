"""Backend-only authentication and checked transport for the Ujin UAE contract."""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError

EMU = Path(__file__).resolve().parents[3] / "emulators"
if str(EMU) not in sys.path:
    sys.path.insert(0, str(EMU))
from ujin_client import UjinClient


class UjinError(RuntimeError):
    def __init__(self, message, *, auth=False):
        super().__init__(message)
        self.auth = auth


class UjinAdapter:
    def __init__(self):
        access = {}
        self.config_error = None
        if os.getenv("UJIN_ACCESS_FILE"):
            try:
                access = json.loads(Path(os.environ["UJIN_ACCESS_FILE"]).read_text(encoding="utf-8-sig"))
                if not isinstance(access, dict):
                    raise ValueError("Expected object")
            except (OSError, ValueError):
                access = {}
                self.config_error = "Не удалось прочитать файл доступов Ujin. Проверьте UJIN_ACCESS_FILE."
        employee = access.get("employee") or {}
        self.base = os.getenv("UJIN_BASE_URL", access.get("api_base") or
                              "https://api-uae-test.ujin.tech").rstrip("/").removesuffix("/api")
        self.apartment_id = str(os.getenv("UJIN_APARTMENT_ID") or access.get("team_apartment") or "")
        self.ust = os.getenv("UJIN_UST", "")
        self.login = os.getenv("UJIN_LOGIN") or employee.get("login") or ""
        self.password = os.getenv("UJIN_PASSWORD") or employee.get("password") or ""
        self.auth_app = os.getenv("UJIN_AUTH_APP") or employee.get("app") or "employee"
        resident = next((row for row in access.get("residents", [])
                         if str(row.get("apartment_id")) == self.apartment_id), {})
        self.control_ust = os.getenv("UJIN_CONTROL_UST") or resident.get("ust") or ""
        self.model_class = os.getenv("UJIN_MODEL_CLASS", "integrations_devices")
        self.enabled = os.getenv("APP_MODE", "local").lower() == "live"
        self._client = None
        self._lock = threading.RLock()

    @property
    def configured(self):
        return bool(self.apartment_id and (self.ust or (self.login and self.password)))

    def status(self):
        return {"configured": self.configured, "enabled": self.enabled, "connected": None,
                "mode": "LIVE" if self.enabled and self.configured else "LOCAL",
                "base_url": self.base, "apartment_id": self.apartment_id,
                "message": self.config_error or ("Доступы заданы. Обмен ещё не проверен." if self.configured else
                           "Укажите файл доступов или UJIN_UST и UJIN_APARTMENT_ID в backend/.env")}

    def safe_message(self, value):
        message = str(value)
        for secret in (self.ust, self.control_ust, self.password, self.login):
            if secret:
                message = message.replace(str(secret), "[скрыто]")
        return re.sub(r"(?:ust|cos|dev)-[\w-]+", "[токен скрыт]", message)[:400]

    @staticmethod
    def public(value):
        if isinstance(value, dict):
            if str(value.get("name", "")).split("_")[-1] in ("token", "password"):
                return {"name": value["name"], "redacted": True}
            return {k: UjinAdapter.public(v) for k, v in value.items()
                    if k != "connection" and not any(s in k.lower() for s in ("token", "password", "authkey"))}
        if isinstance(value, list):
            return [UjinAdapter.public(v) for v in value]
        if isinstance(value, str):
            return re.sub(r"(?:ust|cos|dev)-[\w-]+", "[токен скрыт]", value)
        return value

    def checked(self, response):
        if not isinstance(response, dict) or "error" not in response:
            raise UjinError("Ujin вернул ответ неизвестного формата")
        if response["error"] not in (False, 0, "0", None):
            message = self.safe_message(response.get("message") or "Ujin отклонил запрос")
            raise UjinError(message, auth=bool(re.search(r"авторизац|unauthoriz|invalid token", message, re.I)))
        return response

    def client(self):
        if not self.configured:
            raise UjinError("Для LIVE настройте доступы в backend/.env")
        with self._lock:
            if self._client is None:
                client = UjinClient(self.base, device_token="", dry_run=False, timeout=8,
                                    cls=self.model_class, signal_prefix=self.model_class + "_",
                                    logger=lambda _: None)
                client._journal = lambda *_: None
                if not self.ust:
                    response = self.checked(client.authenticate(self.login, self.password, self.auth_app))
                    data = response.get("data") or {}
                    self.ust = str(data.get("token") or (data.get("user") or {}).get("token")
                                   or response.get("token") or "")
                    if not self.ust:
                        raise UjinError("Ujin не вернул пользовательский токен")
                client.ust, client.apartment_id = self.ust, self.apartment_id
                client._journal = lambda *_: None
                self._client = client
            return self._client

    def call(self, method, *args, **kwargs):
        with self._lock:
            try:
                client = self.client()
                if args and args[0] is None and method in ("get_device_info", "get_devices", "send_signal"):
                    args = (self.ust, *args[1:])
                return self.checked(getattr(client, method)(*args, **kwargs))
            except HTTPError as exc:
                if exc.code == 401 and self.login and self.password:
                    self.ust, self._client = "", None
                raise UjinError(f"Ujin: HTTP {exc.code}") from None
            except UjinError as exc:
                if exc.auth and self.login and self.password:
                    self.ust, self._client = "", None
                raise
            except (URLError, TimeoutError, OSError, ValueError):
                raise UjinError("Нет связи с Ujin. Обмен будет повторён автоматически.") from None
            finally:
                if self._client:
                    self._client.calls.clear()

    def read_device(self, serial):
        return self.call("get_device_info", None, serial)

    def list_devices(self):
        return self.public(self.call("get_devices", None))

    def send_signal(self, serial, signal, value):
        signal = signal.removeprefix(self.model_class + "_")
        return self.public(self.call("send_signal", self.control_ust or None, serial, signal, value))

    def publish(self, rows, new_short=(), serialnumber=""):
        return self.call("publish_group", rows, new_short=new_short, serialnumber=serialnumber)
