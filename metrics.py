"""Collecte de métriques pour le dashboard (thread-safe)."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

# Fenêtre pour considérer un utilisateur « actif » (secondes)
ACTIVE_USER_TTL = 300

# Taille max du journal des requêtes
MAX_LOG_ENTRIES = 10_000

# Historique minute par minute : 7 jours
MAX_MINUTE_BUCKETS = 7 * 24 * 60

_lock = threading.RLock()

_minute_buckets: deque[dict[str, Any]] = deque(maxlen=MAX_MINUTE_BUCKETS)
_current_minute_start: int = 0
_current_total: int = 0
_current_blocked: int = 0

_request_logs: deque[dict[str, Any]] = deque(maxlen=MAX_LOG_ENTRIES)

_user_total_requests: dict[str, int] = {}
_user_blocked_hits: dict[str, int] = {}
_user_last_seen: dict[str, float] = {}
_user_over_limit_flag: dict[str, bool] = {}


def _roll_minute_locked(now: float) -> None:
    """Appelé avec _lock déjà pris."""
    global _current_minute_start, _current_total, _current_blocked
    minute = int(now // 60) * 60
    if _current_minute_start == 0:
        Z = minute
        _current_minute_start = Z
        return
    if minute > _current_minute_start:
        _minute_buckets.append(
            {
                "ts": _current_minute_start,
                "requests": _current_total,
                "blocked": _current_blocked,
            }
        )
        _current_minute_start = minute
        _current_total = 0
        _current_blocked = 0


def record_request(client_key: str, path: str, status_code: int, limit: int, usage_after: int) -> None:
    """
    usage_after: requêtes dans la fenêtre Redis après cet appel (pour les 429: égal à la limite).
    """
    global _current_total, _current_blocked
    now = time.time()
    over = usage_after >= limit or status_code == 429
    with _lock:
        _roll_minute_locked(now)
        _current_total += 1
        if status_code == 429:
            _current_blocked += 1
            _user_blocked_hits[client_key] = _user_blocked_hits.get(client_key, 0) + 1

        _user_total_requests[client_key] = _user_total_requests.get(client_key, 0) + 1
        _user_last_seen[client_key] = now
        if over:
            _user_over_limit_flag[client_key] = True
        elif usage_after < limit:
            _user_over_limit_flag[client_key] = False

        _request_logs.append(
            {
                "ts": now,
                "client_key": client_key,
                "path": path,
                "status_code": status_code,
            }
        )


def snapshot_global(now: float | None = None) -> dict[str, Any]:
    t = now if now is not None else time.time()
    with _lock:
        _roll_minute_locked(t)
        active = sum(1 for last in _user_last_seen.values() if t - last <= ACTIVE_USER_TTL)
        return {
            "requests_this_minute": _current_total,
            "blocked_this_minute": _current_blocked,
            "active_users": active,
            "minute_start": _current_minute_start,
        }


def snapshot_traffic_series(max_points: int | None = None) -> list[dict[str, Any]]:
    t = time.time()
    with _lock:
        _roll_minute_locked(t)
        rows = list(_minute_buckets)
        rows.append(
            {
                "ts": _current_minute_start,
                "requests": _current_total,
                "blocked": _current_blocked,
            }
        )
    if max_points is not None and len(rows) > max_points:
        rows = rows[-max_points:]
    return rows


def filter_logs(
    client_key: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    with _lock:
        logs = list(_request_logs)
    logs.reverse()
    out: list[dict[str, Any]] = []
    for row in logs:
        if client_key and row["client_key"] != client_key:
            continue
        if from_ts is not None and row["ts"] < from_ts:
            continue
        if to_ts is not None and row["ts"] > to_ts:
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


def list_user_keys() -> list[str]:
    with _lock:
        return list(_user_last_seen.keys())


def user_alert_flags() -> dict[str, bool]:
    with _lock:
        return dict(_user_over_limit_flag)


def user_rollups() -> dict[str, dict[str, int]]:
    with _lock:
        return {
            k: {
                "total_recorded": _user_total_requests.get(k, 0),
                "blocked_hits": _user_blocked_hits.get(k, 0),
            }
            for k in _user_last_seen
        }
