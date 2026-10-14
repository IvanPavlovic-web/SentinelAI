"""Simple in-process WebSocket connection manager.

Design choice (documented in README): rather than wiring Redis pub/sub for
WebSocket fan-out (which adds another moving part for a CS50/demo-scale
project), each WebSocket connection has its own lightweight polling loop
that reads the relevant DB row(s) every ~1s and pushes updates to the
connected client. This is simple, robust to a single backend process, and
good enough for a dashboard-style demo. The documented trade-off: it would
not scale horizontally across multiple API replicas without adding Redis
pub/sub (noted as a future improvement in README).
"""
from __future__ import annotations

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.setdefault(channel, []).append(websocket)

    def disconnect(self, channel: str, websocket: WebSocket) -> None:
        conns = self.active_connections.get(channel, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns and channel in self.active_connections:
            del self.active_connections[channel]

    async def broadcast(self, channel: str, message: dict) -> None:
        for connection in list(self.active_connections.get(channel, [])):
            try:
                await connection.send_json(message)
            except Exception:  # noqa: BLE001 - drop dead connections silently
                self.disconnect(channel, connection)


manager = ConnectionManager()
