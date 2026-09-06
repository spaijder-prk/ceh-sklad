from __future__ import annotations

import hmac
import secrets

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse

from .config import settings

SESSION_COOKIE = "ceh_session"
CSRF_COOKIE = "ceh_csrf"
CSRF_HEADER = "X-CSRF-Token"
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_LOGIN_PATHS = {"/api/v1/auth/login", "/api/v1/auth/web-login"}


def _secure_cookie() -> bool:
    return settings.environment == "production"


def set_web_session(response: Response, token: str) -> None:
    max_age = settings.access_token_minutes * 60
    secure = _secure_cookie()
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )


def clear_web_session(response: Response) -> None:
    secure = _secure_cookie()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=secure, httponly=True, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, httponly=False, samesite="strict")


def bearer_from_header(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.casefold() != "bearer" or not token:
        return None
    return token


async def protect_cookie_mutations(request: Request, call_next):
    """Требует double-submit CSRF только для браузерной cookie-сессии."""
    if request.method not in _MUTATING_METHODS or request.url.path in _LOGIN_PATHS:
        return await call_next(request)

    session_token = request.cookies.get(SESSION_COOKIE)
    authorization = request.headers.get("Authorization")
    if not session_token or bearer_from_header(authorization) is not None:
        return await call_next(request)

    expected = request.cookies.get(CSRF_COOKIE)
    provided = request.headers.get(CSRF_HEADER)
    if not expected or not provided or not hmac.compare_digest(expected, provided):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Некорректный CSRF-токен браузерной сессии"},
        )

    origin = request.headers.get("Origin")
    if origin and origin not in settings.cors_origins:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Источник браузерного запроса не разрешен"},
        )

    return await call_next(request)
