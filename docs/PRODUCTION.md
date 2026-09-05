# Production-развертывание

## Рекомендуемый вариант

В репозитории есть отдельный `docker-compose.production.yml`. В нем PostgreSQL и FastAPI находятся только во внутренней Docker-сети, а наружу публикуются только порты `80/443` контейнера Caddy. Caddy получает TLS-сертификат и проксирует `/api/*`, `/health` и `/health/*` в backend, включая WebSocket upgrade, а остальные запросы — в статическую web-панель.

## Подготовка DNS и сервера

До первого запуска:

1. направьте A/AAAA-запись рабочего домена на сервер;
2. откройте входящие TCP `80` и `443`, а также UDP `443` при использовании HTTP/3;
3. не публикуйте `5432` и `8000` в интернет;
4. установите Docker Engine и Docker Compose plugin;
5. создайте отдельный каталог для deployment и ограничьте доступ к `.env.production`.

## Быстрая безопасная подготовка `.env.production`

Чтобы не придумывать и не URL-encode пароли вручную, используйте встроенный генератор:

```bash
python scripts/prepare_production_env.py \
  --domain sklad.example.ru \
  --email admin@example.ru
```

Скрипт:

- принимает только полноценное DNS-имя без `https://`, пути и порта;
- отказывается использовать `localhost`, `.invalid` и тестовые example-домены;
- локально генерирует отдельные случайные пароли/ключи для PostgreSQL, JWT, bootstrap-admin и 1С;
- корректно URL-encode пароль PostgreSQL в `DATABASE_URL`;
- создаёт `.env.production` с правами `0600`;
- никогда не перезаписывает уже существующий файл и не печатает секреты в консоль.

Перед запуском сохраните `BOOTSTRAP_ADMIN_PASSWORD` из `.env.production` в менеджер паролей. После первого входа администратор должен сменить временный bootstrap-пароль.

Если требуется полностью ручная настройка, можно использовать шаблон из следующего раздела.

## Обязательные настройки

Скопируйте шаблон и замените все значения-заглушки:

```bash
cp .env.production.example .env.production
```

Ключевые параметры:

```env
CEH_DOMAIN=sklad.example.ru
ACME_EMAIL=admin@example.ru
POSTGRES_PASSWORD=<сложный пароль>
DATABASE_URL=postgresql+asyncpg://ceh:<URL-encoded пароль>@db:5432/ceh_sklad
JWT_SECRET=<случайный секрет не короче 32 символов>
INTEGRATION_1C_API_KEY=<отдельный ключ для 1С>
BOOTSTRAP_ADMIN_LOGIN=admin
BOOTSTRAP_ADMIN_PASSWORD=<уникальный сложный пароль>
```

Если пароль БД содержит `@`, `:`, `/`, `#` или другие специальные символы, в `DATABASE_URL` используйте URL-encoded представление пароля.

При `ENVIRONMENT=production` backend дополнительно откажется запускаться с дефолтным JWT-секретом, стандартным bootstrap-паролем, тестовым ключом 1С или HTTP-адресом в CORS. Production Compose требует критичные переменные еще до запуска контейнеров.

## Проверка конфигурации

Перед запуском проверьте итоговый Compose:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml config
```

В выводе не должно быть внешних `ports` у `db` и `backend`.

## Первый запуск

```bash
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

Backend при старте автоматически выполняет `alembic upgrade head`, после чего запускает FastAPI. Первый администратор создается только если его еще нет. Caddy начинает обслуживать трафик только после успешного backend healthcheck.

Проверьте состояние:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml ps
curl --fail https://sklad.example.ru/health
curl --fail https://sklad.example.ru/health/ready
```

`/health` — liveness процесса. `/health/ready` дополнительно делает запрос в PostgreSQL и возвращает `schema_revision`; его следует использовать для readiness/мониторинга.

## HTTPS и WebSocket

Caddy автоматически получает и обновляет сертификат для `CEH_DOMAIN`. WebSocket `wss://<домен>/api/v1/realtime` идет через тот же reverse proxy без отдельного внешнего порта.

Release Android должен использовать этот же HTTPS origin:

```bash
gradle -p android :app:assembleRelease -PCEH_API_BASE_URL=https://sklad.example.ru/
```

Web-панель при production Docker build получает `VITE_API_BASE_URL=https://<домен>/api/v1`; сборка с HTTP URL запрещена.

## База данных и резервные копии

- PostgreSQL хранится в volume `ceh_postgres` и не публикует порт наружу.
- Перед обновлением выполняйте резервную копию по `docs/BACKUP.md`.
- CI создает custom-format dump, восстанавливает его в отдельную БД и проверяет Alembic revision и наличие актуальных колонок схемы.
- Для реального восстановления используйте отдельное окно обслуживания и после restore снова выполните `alembic upgrade head`.

## Секреты

Пароли БД, JWT secret, ключ 1С и ключ подписи Android нельзя хранить в Git. Для CI/CD используйте GitHub Secrets или секрет-хранилище инфраструктуры. Файл `.env.production` также нельзя коммитить.

## Проверка после развертывания

1. `GET /health` возвращает `{"status":"ok"}` через HTTPS.
2. `GET /health/ready` возвращает `status=ready`, `database=ok` и текущую Alembic revision.
3. Вход администратора работает только с рабочими учетными данными.
4. Web-панель открывается с рабочего домена и не содержит `localhost` API.
5. WebSocket `wss://.../api/v1/realtime` подключается из Android.
6. 1С проходит проверку отдельного `X-1C-Key`.
7. Тестовая продажа изменяет остаток и появляется в журнале/отчете.
8. Выполнен staging load-test по `docs/LOAD_TEST.md`.
9. Выполнен Android instrumented smoke workflow.
