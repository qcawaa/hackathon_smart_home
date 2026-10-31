"""JSON storage with atomic replacement for the local MVP."""
from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any


class Storage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def read(self, name: str, default: Any):
        path = self.root / name
        with self._lock:
            if not path.exists():
                self.write(name, default)
                return default
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return default

    def write(self, name: str, value: Any) -> None:
        path = self.root / name
        tmp = path.with_suffix(path.suffix + ".tmp")
        content = json.dumps(value, ensure_ascii=False, indent=2)
        with self._lock:
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, path)
