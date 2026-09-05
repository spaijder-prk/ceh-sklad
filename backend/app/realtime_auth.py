from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError

from .config import settings
from .models import User, UserRole


REALTIME_TICKET_SECONDS = 60
TICKET_TYPE = "realtime_ws"
_used_ticket_ids: dict[str, datetime] = {}


def create_realtime_ticket(user: User) -> str:
    if user.role not in {UserRole.ADMIN, UserRole.MANAGER}:
        raise ValueError("WebSocket-ticket доступен только администратору и руководителю")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=REALTIME_TICKET_SECONDS)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "token_type": TICKET_TYPE,
        "jti": str(uuid4()),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def consume_realtime_ticket(token: str) -> UUID:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("token_type") != TICKET_TYPE:
        raise InvalidTokenError("Неверный тип WebSocket-ticket")
    if payload.get("role") not in {UserRole.ADMIN.value, UserRole.MANAGER.value}:
        raise InvalidTokenError("Недопустимая роль WebSocket-ticket")

    ticket_id = payload.get("jti")
    if not isinstance(ticket_id, str) or not ticket_id:
        raise InvalidTokenError("WebSocket-ticket не содержит идентификатор")

    now = datetime.now(timezone.utc)
    expired_ids = [ticket for ticket, expires_at in _used_ticket_ids.items() if expires_at <= now]
    for expired_id in expired_ids:
        _used_ticket_ids.pop(expired_id, None)

    if ticket_id in _used_ticket_ids:
        raise InvalidTokenError("WebSocket-ticket уже использован")

    expires_at_raw = payload.get("exp")
    if not isinstance(expires_at_raw, (int, float)):
        raise InvalidTokenError("WebSocket-ticket не содержит срок действия")
    _used_ticket_ids[ticket_id] = datetime.fromtimestamp(expires_at_raw, tz=timezone.utc)

    try:
        return UUID(payload["sub"])
    except (KeyError, TypeError, ValueError) as error:
        _used_ticket_ids.pop(ticket_id, None)
        raise InvalidTokenError("WebSocket-ticket не содержит пользователя") from error


def reset_used_realtime_tickets_for_tests() -> None:
    _used_ticket_ids.clear()
