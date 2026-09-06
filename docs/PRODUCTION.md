# Production-развертывание по IP и порту

## Рекомендуемый вариант

Production `ceh-sklad` работает без DNS-домена. Клиенты используют один HTTPS origin вида `https://<PUBLIC_IP>:<PORT>`.

В `docker-compose.production.yml` PostgreSQL и FastAPI остаются только во внутренней Docker-сети. Наружу публикуются:

- TCP `80` контейнера Caddy — только для ACME HTTP-01 и HTTP → HTTPS redirect;
- выбранный `CEH_PUBLIC_PORT` → внутренний HTTPS `443` Caddy;
- тот же UDP-порт для HTTP/3.

PostgreSQL `5432` и backend `8000` наружу не публикуются.

Caddy закреплён на `2.11.3-alpine` и запрашивает публично доверенный сертификат Let’s Encrypt непосредственно для IP через ACME profile `shortlived`. IP-сертификаты Let’s Encrypt короткоживущие, поэтому TCP `80` должен оставаться доступным снаружи для автоматического продления. TLS-ALPN challenge отключён намеренно: рабочий HTTPS может находиться не на внешнем `443`.

> Если IP приватный (`10/8`, `172.16/12`, `192.168/16`, loopback, link-local и т. п.) или TCP `80` невозможно направить на Caddy, этот production-профиль не подходит. Не переходите на HTTP. Для такого варианта нужен отдельный внутренний CA/certificate-pinning контур.

## Подготовка сети и сервера

До первого запуска:

1. выделите стабильный публичный IPv4 или IPv6 production host;
2. определите внешний HTTPS-порт приложения, например `8443` или стандартный `443`;
3. направьте входящий TCP `80` на TCP `80` этого host для ACME HTTP-01;
4. направьте выбранный внешний HTTPS-порт на host; Compose сам перенаправит его во внутренний `443` Caddy;
5. при необходимости откройте тот же UDP-порт для HTTP/3;
6. не публикуйте `5432` и `8000` в интернет;
7. установите Docker Engine и Docker Compose plugin;
8. проверьте корректное системное время/NTP;
9. создайте отдельный каталог deployment и ограничьте доступ к `.env.production`.

Порт `80` нельзя использовать как `CEH_PUBLIC_PORT`, потому что он зарезервирован для ACME HTTP-01.

## Быстрая безопасная подготовка `.env.production`

Используйте встроенный генератор:

```bash
python scripts/prepare_production_env.py \
  --ip <REAL_PUBLIC_IP> \
  --port <REAL_HTTPS_PORT> \
  --email <REAL_ACME_EMAIL>
```

Например, если рабочий адрес будет `https://198.51.100.25:8443` (пример адреса замените на реальный), генератор создаст согласованные параметры:

```text
CEH_PUBLIC_IP=<raw IP>
CEH_PUBLIC_HOST=<IP или [IPv6]>
CEH_PUBLIC_PORT=<port>
CEH_PUBLIC_ORIGIN=https://<IP>:<port>
CEH_PUBLIC_WS_ORIGIN=wss://<IP>:<port>
```

Скрипт:

- принимает только глобально маршрутизируемый публичный IPv4/IPv6;
- проверяет диапазон порта и запрещает HTTPS на `80`;
- корректно добавляет `[]` вокруг IPv6 в URL;
- локально генерирует отдельные случайные пароли/ключи для PostgreSQL, JWT, bootstrap-admin и 1С;
- корректно URL-encode пароль PostgreSQL в `DATABASE_URL`;
- создаёт `.env.production` с правами `0600`;
- никогда не перезаписывает уже существующий файл и не печатает секреты в консоль.

Перед запуском сохраните `BOOTSTRAP_ADMIN_PASSWORD` из `.env.production` в менеджер паролей. После первого входа администратор должен сменить временный bootstrap-пароль, выйти и подтвердить повторный вход новым паролем. После этого удалите из `.env.production` обе строки `BOOTSTRAP_ADMIN_LOGIN` и `BOOTSTRAP_ADMIN_PASSWORD` и повторно примените Compose.

Если требуется полностью ручная настройка, используйте `.env.production.example`, заменив документационный TEST-NET IP и все значения-заглушки.

## Обязательные настройки

Ключевые параметры первого запуска:

```env
CEH_PUBLIC_IP=<реальный публичный IP>
CEH_PUBLIC_HOST=<IPv4 либо [IPv6]>
CEH_PUBLIC_PORT=<внешний HTTPS-порт>
CEH_PUBLIC_ORIGIN=https://<IP>:<порт>
CEH_PUBLIC_WS_ORIGIN=wss://<IP>:<порт>
ACME_EMAIL=<контактный email ACME>
POSTGRES_PASSWORD=<сложный пароль>
DATABASE_URL=postgresql+asyncpg://ceh:<URL-encoded пароль>@db:5432/ceh_sklad
JWT_SECRET=<случайный секрет не короче 32 символов>
INTEGRATION_1C_API_KEY=<отдельный ключ для 1С>
BOOTSTRAP_ADMIN_LOGIN=admin
BOOTSTRAP_ADMIN_PASSWORD=<уникальный сложный пароль>
```

`CEH_PUBLIC_HOST`, `CEH_PUBLIC_ORIGIN` и `CEH_PUBLIC_WS_ORIGIN` не должны придумывать вручную независимо от IP/порта: `deploy_production.py` проверяет их на точное совпадение и fail-closed останавливается при drift.

`BOOTSTRAP_ADMIN_LOGIN` и `BOOTSTRAP_ADMIN_PASSWORD` нужны только для создания первого администратора. После подтвержденной смены пароля обе переменные должны быть удалены из production env одновременно. Backend валидирует их как пару: нельзя оставить только одну.

При `ENVIRONMENT=production` backend откажется запускаться с дефолтным JWT-секретом, стандартным bootstrap-паролем, тестовым ключом 1С или HTTP-адресом в CORS. Bootstrap-пара допускается пустой после первичной инициализации.

## Проверка сервера без изменений

Перед первым запуском или обновлением выполните read-only preflight:

```bash
python scripts/deploy_production.py --check-only
```

Команда проверяет:

- права `.env.production`;
- что IP публичный;
- что IP/port/origin/WSS-origin согласованы;
- доступность Docker daemon и Docker Compose;
- итоговый production Compose.

Backup, build, запуск и остановка контейнеров в этом режиме не выполняются. Внешнюю доступность TCP `80` нужно отдельно проверить **с другой сети**: локальная проверка на самом сервере не доказывает прохождение NAT/firewall.

Для ручной диагностики Compose:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml config
```

В выводе не должно быть внешних `ports` у `db` и `backend`.

## Первый запуск и обновление

```bash
python scripts/deploy_production.py
```

При обновлении работающей установки скрипт автоматически делает production-backup БД, затем собирает/поднимает контейнеры и ждёт успешные внешние HTTPS `/health` и `/health/ready` через точный `CEH_PUBLIC_ORIGIN` с версией из `VERSION`. Для первого запуска backup не требуется.

Ручной эквивалент базового запуска:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

Backend при старте выполняет `alembic upgrade head`. Caddy начинает обслуживать прикладной трафик после backend healthcheck и получает/обновляет IP-сертификат автоматически.

После первого входа и смены пароля:

```bash
# Удалите обе строки BOOTSTRAP_ADMIN_* из .env.production
python scripts/deploy_production.py --skip-backup --no-build
```

Bootstrap credentials являются временным секретом первого запуска. Существующий администратор хранится в PostgreSQL; удаление bootstrap-пары не удаляет пользователя и не сбрасывает новый пароль.

## HTTPS и WebSocket

Рабочий origin задаётся один раз в `.env.production`:

```text
CEH_PUBLIC_ORIGIN=https://IP:PORT
CEH_PUBLIC_WS_ORIGIN=wss://IP:PORT
```

CORS backend, production web bundle, CSP и Caddy используют эти значения согласованно. WebSocket идёт через тот же внешний IP/порт:

```text
wss://IP:PORT/api/v1/realtime
```

JWT не помещается в WebSocket URL: Android/staging передают его в `Authorization` header, web использует защищённую session cookie.

Проверка после запуска:

```bash
curl --fail https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/health
curl --fail https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/health/ready
```

Если порт `443`, `:443` можно не указывать.

## Android production release

Release Android должен использовать тот же HTTPS origin:

```bash
./android/gradlew -p android :app:assembleRelease \
  -PCEH_API_BASE_URL=https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/
```

Рекомендуемый путь — workflow `Подписанный Android release`. Перед декодированием keystore он вызывает `scripts/verify_release_backend.py`, который принимает HTTPS origin с IP и портом и требует точное совпадение backend version + Alembic head.

Web-панель при production Docker build получает `VITE_API_BASE_URL=${CEH_PUBLIC_ORIGIN}/api/v1`; HTTP URL запрещён.

## База данных, backup и monitoring

- PostgreSQL хранится в volume `ceh_postgres` и не публикуется наружу.
- `deploy_production.py` делает backup перед обычным обновлением уже работающей БД.
- `scripts/backup.sh --production` валидирует custom-format dump, формирует SHA-256 и metadata.
- `scripts/backup_offsite.sh` отправляет проверенный backup во внешний каталог или `rclone` remote.
- `scripts/production_monitor.py` должен быть настроен на фактический `https://IP:PORT` origin.
- restore drill выполняется в отдельной БД/контуре, не поверх production.

## Проверка после развертывания

1. `GET /health` возвращает `status=ok` через HTTPS по IP:port.
2. `GET /health/ready` возвращает `status=ready`, `database=ok`, версию и текущую Alembic revision.
3. TLS-сертификат публично доверен и содержит фактический IP в SAN.
4. Вход администратора работает с новым постоянным паролем, `BOOTSTRAP_ADMIN_*` отсутствуют в production env.
5. Web-панель использует production IP:port и не содержит localhost API.
6. WebSocket `wss://IP:PORT/api/v1/realtime` работает без токена в URL.
7. Порты `5432` и `8000` недоступны извне.
8. TCP `80` доходит только до Caddy и остаётся доступным для автоматического ACME renewal.
9. Backup + off-site + restore drill и production monitoring проверены.
10. После этого выполняются подписанный Android release и physical-device UAT.

Полная последовательность допуска описана в `docs/GO_LIVE.md`.
