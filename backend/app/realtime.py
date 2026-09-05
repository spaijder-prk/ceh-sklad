import asyncio
import json
import logging
from uuid import uuid4

import redis.asyncio as redis
from fastapi import WebSocket

from .config import settings
from .observability import (
    REALTIME_MESSAGES,
    REALTIME_REDIS_CONNECTED,
    REALTIME_REDIS_PUBLISH_FAILURES,
    WEBSOCKET_CONNECTIONS,
)


logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(
        self,
        *,
        redis_url: str | None = None,
        redis_channel: str | None = None,
    ) -> None:
        self._connections: set[WebSocket] = set()
        self._redis_url = settings.redis_url if redis_url is None else redis_url
        self._redis_channel = redis_channel or settings.redis_channel
        self._origin = uuid4().hex
        self._redis: redis.Redis | None = None
        self._pubsub = None
        self._listener_task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._redis_url or self._redis is not None:
            return

        REALTIME_REDIS_CONNECTED.set(0)
        client = redis.from_url(self._redis_url, decode_responses=True)
        await client.ping()
        pubsub = client.pubsub()
        await pubsub.subscribe(self._redis_channel)
        self._redis = client
        self._pubsub = pubsub
        self._listener_task = asyncio.create_task(
            self._listen_redis(),
            name="ceh-realtime-redis-listener",
        )
        REALTIME_REDIS_CONNECTED.set(1)
        logger.info("Подключен Redis fan-out канала %s", self._redis_channel)

    async def stop(self) -> None:
        task = self._listener_task
        self._listener_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe(self._redis_channel)
            finally:
                await self._pubsub.aclose()
            self._pubsub = None

        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        REALTIME_REDIS_CONNECTED.set(0)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        WEBSOCKET_CONNECTIONS.set(len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)
        WEBSOCKET_CONNECTIONS.set(len(self._connections))

    async def broadcast(self, message: dict) -> None:
        REALTIME_MESSAGES.labels(source="local").inc()
        await self._broadcast_local(message)

        if self._redis is None:
            return
        envelope = json.dumps(
            {"origin": self._origin, "message": message},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            await self._redis.publish(self._redis_channel, envelope)
        except Exception:
            REALTIME_REDIS_PUBLISH_FAILURES.inc()
            # Локальные клиенты уже получили событие; сбой брокера не должен откатывать учетную операцию.
            logger.exception("Не удалось опубликовать real-time событие в Redis")

    async def _broadcast_local(self, message: dict) -> None:
        disconnected: list[WebSocket] = []
        for websocket in tuple(self._connections):
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)

    async def _listen_redis(self) -> None:
        if self._pubsub is None:
            return

        while True:
            try:
                item = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                REALTIME_REDIS_CONNECTED.set(1)
                if item is None:
                    continue
                data = item.get("data")
                if not isinstance(data, str):
                    continue
                await self._relay_redis_payload(data)
            except asyncio.CancelledError:
                raise
            except Exception:
                REALTIME_REDIS_CONNECTED.set(0)
                logger.exception("Ошибка чтения Redis Pub/Sub; повтор через секунду")
                await asyncio.sleep(1)

    async def _relay_redis_payload(self, raw: str) -> None:
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Получено некорректное real-time сообщение из Redis")
            return

        if envelope.get("origin") == self._origin:
            return
        message = envelope.get("message")
        if not isinstance(message, dict):
            return
        REALTIME_MESSAGES.labels(source="redis").inc()
        await self._broadcast_local(message)


stock_updates = ConnectionManager()
