"""JSON storage with atomic replacement for the local MVP."""
from __future__ import annotations

import json
import os
import time
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
            # OneDrive/antivirus can briefly hold the destination on Windows.
            # Keep atomic replacement and a bounded retry; persistent errors surface.
            for attempt in range(6):
                try:
                    os.replace(tmp, path)
                    break
                except PermissionError:
                    if attempt == 5:
                        raise
                    time.sleep(.01 * 2 ** attempt)
