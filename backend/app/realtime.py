import asyncio
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket


class RealtimeHub:
    def __init__(self) -> None:
        self._all: set[WebSocket] = set()
        self._by_location: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, location_id: UUID | None = None) -> None:
        await websocket.accept()
        async with self._lock:
            self._all.add(websocket)
            if location_id:
                self._by_location[location_id].add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._all.discard(websocket)
            for sockets in self._by_location.values():
                sockets.discard(websocket)

    async def stock_changed(self, location_ids: set[UUID]) -> None:
        payload = {"type": "stock_changed", "location_ids": [str(value) for value in location_ids]}
        targets = set(self._all)
        for location_id in location_ids:
            targets.update(self._by_location.get(location_id, set()))
        dead: list[WebSocket] = []
        for socket in targets:
            try:
                await socket.send_json(payload)
            except Exception:
                dead.append(socket)
        for socket in dead:
            await self.disconnect(socket)


hub = RealtimeHub()
