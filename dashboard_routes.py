"""API REST + WebSocket pour le dashboard."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

import config_store
import metrics
from rate_limiter import get_window_usage

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class LimitUpdate(BaseModel):
    limit: int | None = Field(default=None, ge=1)
    window_seconds: int | None = Field(default=None, ge=1)


class DashboardBroadcaster:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast_snapshot(self) -> None:
        async with self._lock:
            if not self._clients:
                return
            clients = list(self._clients)
        payload = json.dumps(build_full_snapshot())
        dead: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_text(payload)
            except Exception:
                dead.append(client)
        if dead:
            async with self._lock:
                for c in dead:
                    self._clients.discard(c)


broadcaster = DashboardBroadcaster()


def build_full_snapshot() -> dict[str, Any]:
    cfg = config_store.get_config()
    g = metrics.snapshot_global()
    alerts = metrics.user_alert_flags()
    rollups = metrics.user_rollups()
    users: list[dict[str, Any]] = []
    for key in metrics.list_user_keys():
        usage, limit = get_window_usage(key)
        remaining = max(0, limit - usage)
        blocked = usage >= limit or alerts.get(key, False)
        r = rollups.get(key, {"total_recorded": 0, "blocked_hits": 0})
        users.append(
            {
                "client_key": key,
                "usage": usage,
                "limit": limit,
                "remaining": remaining,
                "status": "blocked" if blocked else "ok",
                "total_recorded": r["total_recorded"],
                "blocked_hits": r["blocked_hits"],
            }
        )
    users.sort(key=lambda u: u["usage"], reverse=True)
    return {
        "global": g,
        "config": cfg,
        "users": users,
        "alerts": alerts,
        "server_time": time.time(),
    }


@router.get("/summary")
def dashboard_summary() -> dict[str, Any]:
    return build_full_snapshot()


@router.get("/traffic")
def traffic_history(hours: int = Query(24, ge=1, le=24 * 7)) -> dict[str, Any]:
    max_points = hours * 60
    series = metrics.snapshot_traffic_series(max_points=max_points)
    return {"hours": hours, "series": series}


@router.get("/logs")
def request_logs(
    user: str | None = None,
    from_ts: float | None = Query(default=None, alias="from"),
    to_ts: float | None = Query(default=None, alias="to"),
    limit: int = Query(500, ge=1, le=2000),
) -> dict[str, Any]:
    rows = metrics.filter_logs(client_key=user, from_ts=from_ts, to_ts=to_ts, limit=limit)
    return {"items": rows, "count": len(rows)}


@router.patch("/config")
def patch_config(body: LimitUpdate) -> dict[str, Any]:
    if body.limit is not None:
        config_store.set_limit(body.limit)
    if body.window_seconds is not None:
        config_store.set_window(body.window_seconds)
    return config_store.get_config()


@router.websocket("/ws")
async def dashboard_ws(ws: WebSocket) -> None:
    await broadcaster.connect(ws)
    try:
        await ws.send_text(json.dumps(build_full_snapshot()))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(ws)


async def broadcast_loop() -> None:
    while True:
        await asyncio.sleep(1.0)
        await broadcaster.broadcast_snapshot()
