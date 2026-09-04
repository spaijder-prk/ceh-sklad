from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

import httpx


P = ParamSpec("P")
R = TypeVar("R")
RETRYABLE_HTTP_STATUSES = {408, 425, 429}


@dataclass(frozen=True)
class RemoteFailure:
    retryable: bool
    status_code: int | None
    retry_after_seconds: int | None
    message: str

    @property
    def exit_code(self) -> int:
        return 75 if self.retryable else 2


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> int | None:
    if not value:
        return None
    raw = value.strip()
    if raw.isdigit():
        return max(0, int(raw))
    try:
        target = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    return max(0, math.ceil((target.astimezone(UTC) - current.astimezone(UTC)).total_seconds()))


def classify_remote_error(exc: httpx.HTTPError) -> RemoteFailure:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        retryable = status_code in RETRYABLE_HTTP_STATUSES or 500 <= status_code <= 599
        retry_after = parse_retry_after(exc.response.headers.get("Retry-After")) if retryable else None
        category = "временная" if retryable else "требует вмешательства"
        return RemoteFailure(
            retryable=retryable,
            status_code=status_code,
            retry_after_seconds=retry_after,
            message=f"Удаленный сервис вернул HTTP {status_code}: ошибка {category}",
        )
    if isinstance(exc, httpx.RequestError):
        return RemoteFailure(
            retryable=True,
            status_code=None,
            retry_after_seconds=None,
            message=f"Сетевая ошибка {exc.__class__.__name__}: повтор разрешен",
        )
    return RemoteFailure(
        retryable=False,
        status_code=None,
        retry_after_seconds=None,
        message=f"Неизвестная HTTP-ошибка {exc.__class__.__name__}",
    )


def guarded_remote_cli(fn: Callable[P, R]) -> Callable[P, R]:
    """Единая граница ошибок для консольных команд bridge.

    Код 75 означает временную ошибку и допускает автоматический повтор планировщиком.
    Код 2 означает ошибку прав/данных/контракта, требующую ручного исправления.
    """

    @wraps(fn)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except httpx.HTTPError as exc:
            failure = classify_remote_error(exc)
            suffix = (
                f"; Retry-After={failure.retry_after_seconds}s"
                if failure.retry_after_seconds is not None
                else ""
            )
            print(f"REMOTE_ERROR: {failure.message}{suffix}", file=sys.stderr)
            raise SystemExit(failure.exit_code) from exc

    return wrapped
