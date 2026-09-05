# Production-развертывание

Production-контур состоит из PostgreSQL, Redis, FastAPI backend, Prometheus и Nginx. Nginx раздает собранную веб-панель, завершает TLS и проксирует REST/WebSocket на backend. Redis используется только как общий fan-out real-time событий между экземплярами backend; источником учетных данных остается PostgreSQL. Prometheus собирает технические метрики только внутри Docker-сети.

## 1. Подготовить переменные

```bash
cp .env.production.example .env.production
```

Проверьте имя БД, пользователя, публичные порты, локальный порт Prometheus и пути к TLS-сертификату.

## 2. Создать секреты вне Git

Каталог `secrets/` исключен из Git.

```bash
mkdir -p secrets
openssl rand -base64 48 > secrets/db_password.txt
openssl rand -base64 64 > secrets/jwt_secret.txt
openssl rand -base64 48 > secrets/integration_api_key.txt
openssl rand -base64 48 > secrets/redis_password.txt
chmod 600 secrets/*.txt
```

Если интеграция с 1С должна быть отключена, создайте пустой `secrets/integration_api_key.txt`.

JWT-секрет должен содержать минимум 32 символа. Production backend дополнительно проверяет, что используется PostgreSQL, `CEH_AUTO_CREATE_SCHEMA=false` и JWT-секрет не является тестовым/дефолтным.

## 3. TLS

В `.env.production` укажите существующие файлы сертификата и закрытого ключа, например сертификаты Let's Encrypt:

```text
CEH_TLS_FULLCHAIN_FILE=/etc/letsencrypt/live/sklad.example.ru/fullchain.pem
CEH_TLS_PRIVKEY_FILE=/etc/letsencrypt/live/sklad.example.ru/privkey.pem
```

Сертификаты не копируются в образ и не хранятся в репозитории: Docker Compose передает их Nginx как secrets.

Nginx перенаправляет HTTP на HTTPS, добавляет базовые security headers, обслуживает SPA и отдельно проксирует WebSocket Upgrade для `/api/v1/ws/`.

## 4. Запуск

```bash
docker compose --env-file .env.production -f compose.production.yml build
docker compose --env-file .env.production -f compose.production.yml up -d
```

Backend перед стартом выполняет `alembic upgrade head` и только после успешной миграции запускает Uvicorn. При заданном `CEH_REDIS_URL` приложение подключается к Redis Pub/Sub на startup; если Redis недоступен при старте production-контейнера, health/dependency-механизм Compose не пропустит backend раньше broker.

Prometheus стартует после успешного healthcheck backend и опрашивает внутренний `/metrics` раз в 15 секунд.

## 5. Проверка

```bash
docker compose --env-file .env.production -f compose.production.yml ps
curl -I https://<ваш-домен>/
curl https://<ваш-домен>/health
curl http://127.0.0.1:9090/-/healthy
```

PostgreSQL, Redis и backend имеют контейнерные healthcheck. Внешний доступ к PostgreSQL, Redis и порту backend не публикуется: наружу открыты только Nginx 80/443. Prometheus привязан к `127.0.0.1` production-хоста и также недоступен напрямую из внешней сети.

## Мониторинг

Backend production запускается через `app.observed_app:app`, который добавляет Prometheus-метрики и структурированный JSON request log. Стандартный Uvicorn access log отключен, чтобы один запрос не записывался дважды.

Prometheus читает:

```text
http://backend:8000/metrics
```

Nginx этот маршрут не проксирует. Для удаленного просмотра Prometheus используйте SSH-туннель к loopback-порту, а не открывайте 9090 в интернет.

Подробное описание метрик, `X-Request-ID` и формата логов: `docs/monitoring.md`.

## Real-time и несколько backend

Каждый процесс backend держит только свои WebSocket-соединения. При `CEH_REDIS_URL` событие сначала отправляется локальным клиентам, затем публикуется в общий Redis-канал `ceh-sklad:realtime`. Другие процессы получают его через Pub/Sub и пересылают своим локальным клиентам.

Каждый процесс имеет собственный `origin`, поэтому сообщение, опубликованное им самим, не отправляется его клиентам повторно после возврата из Redis.

Если публикация в Redis временно не удалась уже после проведения учетной транзакции, сама операция не откатывается: локальные клиенты обновляются сразу, а остальные клиенты сохраняют резервный REST-refresh. Для высокой доступности самого broker можно отдельно использовать управляемый Redis/Sentinel/Cluster в соответствии с инфраструктурой площадки.

В development `CEH_REDIS_URL` можно не задавать: приложение сохраняет прежний in-memory режим.

## Обновление

Перед обновлением сохраните резервную копию PostgreSQL. Затем:

```bash
git pull
docker compose --env-file .env.production -f compose.production.yml build
docker compose --env-file .env.production -f compose.production.yml up -d
```

Alembic автоматически применит новые миграции перед запуском новой версии backend.

## Секреты и резервные копии

- не добавляйте `.env.production`, `secrets/`, TLS-ключи и Android keystore в Git;
- храните копию JWT-секрета до завершения срока жизни выпущенных токенов;
- ключ 1С, пароль Redis, JWT и пароль PostgreSQL должны быть разными;
- резервные копии БД храните отдельно от production-хоста и периодически проверяйте восстановление;
- перед ротацией пароля PostgreSQL согласованно обновляйте secret-файл и саму роль БД.
