"""Limites dynamiques modifiables via l'API dashboard."""

from __future__ import annotations

import os
import threading

from dotenv import load_dotenv

load_dotenv()

_lock = threading.Lock()

_default_limit = int(os.getenv("LIMIT", 10))
_default_window = int(os.getenv("WINDOW", 60))
_limit = _default_limit
_window = _default_window


def get_limit() -> int:
    with _lock:
        return _limit


def get_window() -> int:
    with _lock:
        return _window


def set_limit(value: int) -> int:
    global _limit
    v = max(1, int(value))
    with _lock:
        _limit = v
    return _limit


def set_window(value: int) -> int:
    global _window
    v = max(1, int(value))
    with _lock:
        _window = v
    return _window


def get_config() -> dict:
    with _lock:
        return {"limit": _limit, "window_seconds": _window}
