from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .database import SessionFactory
from .models import User


class LoginRetryAfterMiddleware:
    """Добавляет точный Retry-After к 429 блокировки входа.

    Middleware не меняет auth-логику и не логирует request body. Тело запроса
    буферизуется только на время одного login-запроса и полностью переигрывается
    downstream приложению.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/api/v1/auth/login"
        ):
            await self.app(scope, receive, send)
            return

        request_messages: list[Message] = []
        while True:
            message = await receive()
            request_messages.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] == "http.request" and not message.get("more_body", False):
                break

        login = _extract_login(request_messages)
        replay_index = 0

        async def replay_receive() -> Message:
            nonlocal replay_index
            if replay_index < len(request_messages):
                message = request_messages[replay_index]
                replay_index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send_with_retry_after(message: Message) -> None:
            if message["type"] == "http.response.start" and message.get("status") == 429 and login:
                retry_after = await _remaining_lock_seconds(login)
                if retry_after is not None:
                    headers = list(message.get("headers", []))
                    if not any(key.lower() == b"retry-after" for key, _ in headers):
                        headers.append((b"retry-after", str(retry_after).encode("ascii")))
                        message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, replay_receive, send_with_retry_after)


def _extract_login(messages: list[Message]) -> str | None:
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.request"
    )
    if not body:
        return None
    try:
        payload: Any = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    login = payload.get("login")
    return login if isinstance(login, str) and login else None


async def _remaining_lock_seconds(login: str) -> int | None:
    try:
        async with SessionFactory() as session:
            locked_until = await session.scalar(
                select(User.login_locked_until).where(User.login == login)
            )
    except Exception:
        # Ошибка диагностического заголовка не должна подменять исходный auth-ответ.
        return None

    if locked_until is None:
        return None
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    remaining = (locked_until - datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        return None
    return max(1, math.ceil(remaining))
