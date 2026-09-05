import asyncio
import json

from app.realtime import ConnectionManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


def test_local_realtime_broadcast_works_without_redis():
    async def scenario() -> None:
        manager = ConnectionManager(redis_url="")
        websocket = FakeWebSocket()
        await manager.connect(websocket)  # type: ignore[arg-type]
        await manager.broadcast({"type": "state_changed", "stock_changed": True})

        assert websocket.accepted is True
        assert websocket.messages == [
            {"type": "state_changed", "stock_changed": True}
        ]

    asyncio.run(scenario())


def test_external_redis_event_is_relayed_but_own_event_is_ignored():
    async def scenario() -> None:
        manager = ConnectionManager(redis_url="")
        websocket = FakeWebSocket()
        await manager.connect(websocket)  # type: ignore[arg-type]

        await manager._relay_redis_payload(  # noqa: SLF001
            json.dumps(
                {
                    "origin": "other-instance",
                    "message": {"type": "catalog_changed", "product_id": "p1"},
                }
            )
        )
        await manager._relay_redis_payload(  # noqa: SLF001
            json.dumps(
                {
                    "origin": manager._origin,  # noqa: SLF001
                    "message": {"type": "catalog_changed", "product_id": "p2"},
                }
            )
        )

        assert websocket.messages == [
            {"type": "catalog_changed", "product_id": "p1"}
        ]

    asyncio.run(scenario())
