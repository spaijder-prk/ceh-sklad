# Мониторинг и журналы backend

Production backend публикует технические метрики Prometheus и пишет структурированные журналы HTTP-запросов в stdout. Этот контур предназначен для эксплуатации и не меняет бизнес-данные PostgreSQL.

## Prometheus

В `compose.production.yml` добавлен сервис Prometheus. Он опрашивает внутренний маршрут backend:

```text
http://backend:8000/metrics
```

Маршрут `/metrics` не проксируется Nginx и не публикуется в интернет. Веб-интерфейс Prometheus привязан только к loopback production-хоста:

```text
127.0.0.1:9090
```

Порт и срок хранения можно изменить в `.env.production`:

```text
CEH_PROMETHEUS_PORT=9090
CEH_PROMETHEUS_RETENTION=15d
```

Для просмотра с рабочего компьютера используйте SSH-туннель, например:

```bash
ssh -L 9090:127.0.0.1:9090 user@production-host
```

После этого интерфейс доступен локально на `http://127.0.0.1:9090`.

## Основные метрики

Backend экспортирует в том числе:

- `ceh_http_requests_total` — количество HTTP-запросов по методу, шаблону маршрута и статусу;
- `ceh_http_request_duration_seconds` — распределение времени ответа;
- `ceh_http_requests_in_progress` — текущие выполняющиеся HTTP-запросы;
- `ceh_websocket_connections` — активные WebSocket-соединения на экземпляре backend;
- `ceh_realtime_redis_connected` — состояние Redis Pub/Sub;
- `ceh_realtime_redis_publish_failures_total` — ошибки публикации событий в Redis;
- `ceh_realtime_messages_total` — количество real-time событий с разделением локального и Redis-источника;
- стандартные process/Python-метрики библиотеки Prometheus client.

В HTTP-метриках используется шаблон маршрута (`/api/v1/products/{product_id}`), а не фактический URL. Неизвестные пути получают метку `__unmatched__`. Это ограничивает кардинальность и не переносит пользовательские идентификаторы в labels.

## Request ID

Каждый обычный HTTP-ответ backend содержит:

```text
X-Request-ID: <идентификатор>
```

Если клиент передал корректный `X-Request-ID`, backend сохраняет его. Допускаются только ASCII-символы `A-Z`, `a-z`, `0-9`, `.`, `_`, `:`, `-` и длина до 128 символов. Некорректное значение заменяется случайным UUID.

Request ID удобно передавать из reverse proxy, 1С или другого вызывающего сервиса и затем искать тот же идентификатор в централизованных логах.

## Структурированные HTTP-журналы

Production Uvicorn запускается с отключенным стандартным access log. Вместо него middleware приложения пишет по одной JSON-строке на запрос в stdout контейнера backend, например:

```json
{"timestamp":"2026-09-05T10:30:00+00:00","event":"http_request","request_id":"abc-123","method":"GET","route":"/api/v1/products","status":200,"duration_ms":12.345,"client_ip":"172.20.0.5"}
```

В request log намеренно не записываются:

- JWT;
- `X-Integration-Key`;
- пароли;
- тело запроса;
- query string;
- полный URL с потенциальными идентификаторами.

Системные сообщения Uvicorn/FastAPI/Redis продолжают поступать в stderr/stdout контейнера обычным способом.

Просмотр последних логов:

```bash
docker compose --env-file .env.production -f compose.production.yml logs --tail=200 backend
```

Поток логов:

```bash
docker compose --env-file .env.production -f compose.production.yml logs -f backend
```

## Минимальные эксплуатационные сигналы

Для первой production-инсталляции рекомендуется отслеживать как минимум:

1. долю HTTP 5xx;
2. рост p95/p99 времени ответа;
3. `ceh_realtime_redis_connected == 0`;
4. рост `ceh_realtime_redis_publish_failures_total`;
5. отсутствие успешного `/health`;
6. свободное место PostgreSQL и каталога резервных копий;
7. успешность ежедневного backup job.

Prometheus в текущем контуре хранит метрики локально. Долговременное удаленное хранение, Alertmanager и централизованный сбор JSON-логов можно подключить отдельно, не меняя формат метрик или request log.
