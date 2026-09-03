from __future__ import annotations

from fastapi import HTTPException, Request

from .auth import decode_user_id
from .database import SessionFactory
from .models import AuditLog

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def audit_mutations(request: Request, call_next):
    """Фиксирует факт изменения без сохранения тела запроса, паролей, JWT и ключей интеграции."""
    if request.method not in _MUTATING_METHODS:
        return await call_next(request)

    actor_type = "anonymous"
    user_id = None
    if request.url.path.startswith("/api/v1/integration/1c"):
        actor_type = "1c"
    else:
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            try:
                user_id = decode_user_id(token)
                actor_type = "user"
            except HTTPException:
                actor_type = "invalid_token"

    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        try:
            async with SessionFactory() as session:
                session.add(
                    AuditLog(
                        actor_type=actor_type,
                        user_id=user_id,
                        method=request.method,
                        path=request.url.path,
                        status_code=status_code,
                    )
                )
                await session.commit()
        except Exception:
            # Сбой дополнительного аудита не должен превращать успешно проведенную складскую операцию в ошибку HTTP.
            pass
