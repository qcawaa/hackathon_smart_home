from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EMU = ROOT / "emulators"
if str(EMU) not in sys.path:
    sys.path.insert(0, str(EMU))
from ujin_client import UjinClient  # noqa: E402


class UjinAdapter:
    def __init__(self):
        self.base = os.getenv("UJIN_BASE_URL", "https://api-uae-test.ujin.tech")
        self.ust = os.getenv("UJIN_UST", "")
        self.apartment_id = os.getenv("UJIN_APARTMENT_ID", "")
        self.model_class = os.getenv("UJIN_MODEL_CLASS", "integrations_devices")

    @property
    def configured(self):
        return bool(self.ust and self.apartment_id)

    def status(self):
        return {"configured": self.configured, "connected": None,
                "mode": "LIVE" if self.configured else "LOCAL",
                "message": "Доступы заданы; подключение проверяется при запросе" if self.configured else "Работаем локально. Ujin доступы не заданы.",
                "base_url": self.base}

    def client(self):
        if not self.configured:
            raise RuntimeError("Для LIVE укажите UJIN_UST и UJIN_APARTMENT_ID в backend/.env")
        return UjinClient(self.base, dry_run=False, cls=self.model_class,
                          signal_prefix=self.model_class + "_", ust=self.ust,
                          apartment_id=self.apartment_id)

    def read_device(self, serial: str):
        return self.client().get_device_info(self.ust, serial)

    def send_signal(self, serial: str, signal: str, value):
        """Use the starter pack HTTP transport for the documented platform action."""
        return self.client()._get("/api/apartment/send-signal/", {
            "token": self.ust, "serialnumber": serial, "signal": signal, "value": value,
        })
