from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jwt import InvalidTokenError
from pydantic import BaseModel

from .db import SessionLocal
from .models import User, UserRole
from .realtime import stock_updates
from .realtime_auth import (
    REALTIME_TICKET_SECONDS,
    consume_realtime_ticket,
    create_realtime_ticket,
)
from .security import require_roles


router = APIRouter(tags=["Обновления в реальном времени"])
AdminOrManagerDep = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))
]


class RealtimeTicketResponse(BaseModel):
    ticket: str
    expires_in: int


@router.on_event("startup")
async def start_realtime_broker() -> None:
    await stock_updates.start()


@router.on_event("shutdown")
async def stop_realtime_broker() -> None:
    await stock_updates.stop()


@router.post("/auth/ws-ticket", response_model=RealtimeTicketResponse)
def issue_browser_ticket(user: AdminOrManagerDep):
    return RealtimeTicketResponse(
        ticket=create_realtime_ticket(user),
        expires_in=REALTIME_TICKET_SECONDS,
    )


@router.websocket("/ws/browser-updates")
async def browser_updates_websocket(
    websocket: WebSocket,
    ticket: str | None = Query(default=None),
):
    if not ticket:
        await websocket.close(code=4401)
        return

    try:
        user_id = consume_realtime_ticket(ticket)
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        await websocket.close(code=4401)
        return

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            await websocket.close(code=4401)
            return
        if user.role not in {UserRole.ADMIN, UserRole.MANAGER}:
            await websocket.close(code=4403)
            return

    await stock_updates.connect(websocket)
    try:
        await websocket.send_json({"type": "connected", "user_id": str(user_id)})
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        stock_updates.disconnect(websocket)
