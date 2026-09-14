import asyncio
import json

from fastapi import WebSocket


class ConnectionManager:
    """Tracks live WebSocket connections per mandi and fans out events."""

    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, mandi_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(mandi_id, set()).add(websocket)

    def disconnect(self, mandi_id: str, websocket: WebSocket):
        connections = self._connections.get(mandi_id)
        if connections:
            connections.discard(websocket)
            if not connections:
                self._connections.pop(mandi_id, None)

    async def broadcast(self, mandi_id: str, event_type: str, data: dict):
        payload = json.dumps({"type": event_type, "mandi_id": mandi_id, "data": data})
        connections = list(self._connections.get(mandi_id, ()))
        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                self.disconnect(mandi_id, ws)

    def connection_count(self, mandi_id: str) -> int:
        return len(self._connections.get(mandi_id, ()))


manager = ConnectionManager()


def broadcast_sync(mandi_id: str, event_type: str, data: dict):
    """Fire-and-forget broadcast safe to call from sync route handlers."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        asyncio.get_event_loop().create_task(manager.broadcast(mandi_id, event_type, data))
