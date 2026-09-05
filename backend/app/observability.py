import json
import logging
import re
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

HTTP_REQUESTS = Counter(
    "ceh_http_requests_total",
    "Количество HTTP-запросов backend.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "ceh_http_request_duration_seconds",
    "Длительность HTTP-запросов backend в секундах.",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "ceh_http_requests_in_progress",
    "Количество HTTP-запросов, выполняющихся в текущий момент.",
    ("method",),
)
WEBSOCKET_CONNECTIONS = Gauge(
    "ceh_websocket_connections",
    "Количество активных WebSocket-соединений на текущем экземпляре backend.",
)
REALTIME_REDIS_CONNECTED = Gauge(
    "ceh_realtime_redis_connected",
    "Состояние подключения текущего экземпляра backend к Redis Pub/Sub.",
)
REALTIME_REDIS_PUBLISH_FAILURES = Counter(
    "ceh_realtime_redis_publish_failures_total",
    "Количество ошибок публикации real-time событий в Redis.",
)
REALTIME_MESSAGES = Counter(
    "ceh_realtime_messages_total",
    "Количество real-time событий по источнику.",
    ("source",),
)

request_logger = logging.getLogger("ceh.request")
request_logger.setLevel(logging.INFO)
request_logger.propagate = False
if not request_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    request_logger.addHandler(handler)


def request_id_from_header(value: str | None) -> str:
    if value and REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return uuid4().hex


def route_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return "__unmatched__"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        request_id = request_id_from_header(request.headers.get("x-request-id"))
        method = request.method
        started = perf_counter()
        status_code = 500
        response = None
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            elapsed = perf_counter() - started
            route = route_label(request)
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()
            HTTP_REQUESTS.labels(
                method=method,
                route=route,
                status=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION.labels(method=method, route=route).observe(elapsed)

            client = request.client.host if request.client else None
            request_logger.info(
                json.dumps(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event": "http_request",
                        "request_id": request_id,
                        "method": method,
                        "route": route,
                        "status": status_code,
                        "duration_ms": round(elapsed * 1000, 3),
                        "client_ip": client,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )


async def metrics_response() -> Response:
    return Response(
        content=generate_latest(),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )


def install_observability(app: FastAPI) -> None:
    app.add_middleware(ObservabilityMiddleware)
    app.add_api_route(
        "/metrics",
        metrics_response,
        methods=["GET"],
        include_in_schema=False,
        tags=["Система"],
    )
