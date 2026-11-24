"""In-memory (and optional file) request/response log for the inspector."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from typing import Any

from erpbridge.settings import data_dir

_LOCK = threading.Lock()
_ENTRIES: deque[dict[str, Any]] = deque(maxlen=200)
_SEQ = 0


def _log_path() -> str:
    os.makedirs(data_dir(), exist_ok=True)
    return os.path.join(data_dir(), "bridge.jsonl")


def reset() -> None:
    global _SEQ
    with _LOCK:
        _ENTRIES.clear()
        _SEQ = 0


def record(entry: dict[str, Any]) -> dict[str, Any]:
    global _SEQ
    with _LOCK:
        _SEQ += 1
        stored = dict(entry)
        stored.setdefault("id", _SEQ)
        stored.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
        _ENTRIES.appendleft(stored)
        try:
            with open(_log_path(), "a", encoding="utf-8") as handle:
                handle.write(json.dumps(stored, default=str) + "\n")
        except OSError:
            pass
        return stored


def entries() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_ENTRIES)


def latest(n: int = 20) -> list[dict[str, Any]]:
    with _LOCK:
        return list(_ENTRIES)[:n]
