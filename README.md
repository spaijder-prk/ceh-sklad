# Цех Склад

Монорепозиторий системы складского учета для нескольких складов и торговых представителей с Android-клиентом, web-панелью и интеграцией с **1С:Управление нашей фирмой (УНФ) в облаке**.

Текущая версия продукта: **0.4.0**.

## Что входит

- `backend/` — FastAPI + PostgreSQL, транзакционное складское ядро, задолженность, роли, аудит, 1С/УНФ API;
- `android/` — приложение торгового представителя с offline-кэшем, очередью неподтвержденных операций и realtime;
- `admin-web/` — панель администратора/руководителя;
- `unf-bridge/` — bridge к облачной УНФ/1С:Фреш с metadata-driven mapping, dry-run, health и идемпотентным экспортом;
- `docs/` — архитектура, первый запуск, production, backup/restore, staging и интеграция УНФ Cloud;
- `scripts/` — production deploy, backup/restore, load-test, staging smoke, monitoring и release-проверки.

## Основные правила учета

- проведенные документы не редактируются задним числом;
- исправления оформляются отдельной корректировкой;
- остаток изменяется только транзакционно вместе с документом и движениями;
- мобильная операция не уменьшает локальный остаток до подтверждения backend;
- повторная доставка защищена идемпотентным `operation_key`;
- розничная и оптовая цены хранятся отдельно;
- каждому торговому представителю соответствует виртуальный склад `ceh-sklad`.

## Первый локальный запуск

Подробный сценарий: `docs/FIRST_RUN.md`.

```bash
cp .env.example .env
make first-run
```

Без `make`:

```bash
docker compose config --quiet
docker compose up --build -d
```

После запуска:

- web: `http://localhost:5173`;
- backend: `http://localhost:8000`;
- OpenAPI: `http://localhost:8000/docs`.

Development Compose публикует web/API только на `127.0.0.1`, PostgreSQL наружу не публикуется.

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/health/ready
```

## Production без домена: IP + порт

Production не требует DNS-домена. Клиенты используют один HTTPS origin вида:

```text
https://<PUBLIC_IP>:<HTTPS_PORT>
```

Для публично доверенного TLS Caddy получает короткоживущий Let’s Encrypt сертификат непосредственно на IP. TCP `80` должен доходить до Caddy для ACME HTTP-01 и автоматического продления сертификата. Рабочий HTTPS может находиться на другом выбранном внешнем порту, например `8443`.

Подготовьте `.env.production`:

```bash
python scripts/prepare_production_env.py \
  --ip <REAL_PUBLIC_IP> \
  --port <REAL_HTTPS_PORT> \
  --email <REAL_ACME_EMAIL>
```

Генератор создаёт согласованные `CEH_PUBLIC_IP`, `CEH_PUBLIC_HOST`, `CEH_PUBLIC_PORT`, `CEH_PUBLIC_ORIGIN` и `CEH_PUBLIC_WS_ORIGIN`, а также отдельные случайные production secrets. Файл создаётся с правами `0600` и не перезаписывается автоматически.

До любых изменений контейнеров выполните read-only preflight:

```bash
python scripts/deploy_production.py --check-only
```

После проверки внешнего TCP `80` и выбранного HTTPS-порта:

```bash
python scripts/deploy_production.py
```

Deploy проверяет права env, публичность IP, согласованность IP/port/origin, Docker Compose; при обновлении работающей БД делает production backup и ждёт внешние HTTPS `/health` + `/health/ready` с версией из `VERSION`.

Проверка:

```bash
curl --fail https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/health
curl --fail https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/health/ready
```

PostgreSQL `5432` и FastAPI `8000` не должны быть доступны извне. Если IP приватный или TCP `80` невозможно предоставить Caddy, не переключайте production на HTTP: нужен отдельный внутренний CA/certificate-pinning профиль.

Production backup/restore:

```bash
./scripts/backup.sh --production
./scripts/restore.sh --production backups/ceh_sklad_YYYYMMDD_HHMMSS.dump
```

## Backend без Docker

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
pip install --no-deps -e '.[dev]'
alembic upgrade head
uvicorn app.main:app --reload
```

Тесты требуют PostgreSQL:

```bash
pytest -q
```

## Web-панель без Docker

```bash
cd admin-web
npm ci
npm run dev
```

Production build требует явный HTTPS API URL, в том числе IP + порт:

```bash
VITE_API_BASE_URL=https://<PUBLIC_IP>:<HTTPS_PORT>/api/v1 npm run build
```

CI дополнительно проверяет отсутствие `localhost:8000` в production bundle.

## Android

Debug использует emulator URL. Release требует production HTTPS origin и собирается через зафиксированный Gradle Wrapper:

```bash
./android/gradlew -p android :app:assembleRelease \
  -PCEH_API_BASE_URL=https://<PUBLIC_IP>:<HTTPS_PORT>/
```

Подписанный production release создаётся workflow `Подписанный Android release`. До декодирования keystore workflow проверяет фактический production backend: HTTPS, `status=ready`, точную версию продукта и текущий Alembic head. APK/AAB публикуются вместе с manifest и `SHA256SUMS`.

Android поддерживает:

- вход только торгового представителя с привязанным виртуальным складом;
- остатки обычных складов и собственный остаток;
- розничную/оптовую цену;
- продажу, возврат и сдачу денег;
- долг и историю;
- Room-кэш подтвержденных данных;
- Room/WorkManager offline queue;
- WebSocket с переподключением и JWT в `Authorization` header, а не URL;
- защищенную сессию через Android Keystore;
- смену собственного пароля.

Подробности: `docs/ANDROID_RELEASE.md` и `docs/ANDROID_SMOKE.md`.

## 1С:УНФ Cloud

Универсальный обмен находится под `/api/v1/integration/1c`. Для УНФ Cloud реализованы профиль, outbox и идемпотентное подтверждение экспорта. Учетные данные облачной УНФ не хранятся в Android/web; между `ceh-sklad` и конкретным tenant используется `unf-bridge`.

Подробности: `docs/INTEGRATION_UNF_CLOUD.md`, `docs/UNF_BRIDGE_RUNBOOK.md`, `docs/UNF_TENANT_CHECKLIST.md`. Реальное подключение tenant отслеживается в issue #8.

## Безопасность

- роли `representative`, `admin`, `manager` проверяются сервером;
- пароли хэшируются Argon2;
- смена/reset пароля инвалидирует старые REST/WSS сессии;
- browser session использует `HttpOnly`, `SameSite=Strict` и CSRF-проверку;
- JWT не хранится в browser localStorage и не помещается в WebSocket query;
- backend Docker image работает от непривилегированного пользователя;
- release Android запрещает cleartext HTTP;
- Android Auto Backup отключён;
- production Caddy включает TLS/security headers;
- Caddy закреплён на проверяемой версии и использует ACME `shortlived` для IP certificate;
- PostgreSQL/FastAPI не публикуются напрямую наружу;
- signing keys, реальные env, backup и release artifacts исключены из Git.

## Эксплуатация

- `/health` — liveness + версия продукта;
- `/health/ready` — PostgreSQL + Alembic revision + версия;
- `/api/v1/system/status` — admin/manager: очередь обмена, ошибки 1С, заблокированные аккаунты и готовность сопоставлений УНФ;
- `scripts/production_monitor.py` использует `CEH_PUBLIC_ORIGIN=https://IP:PORT` либо явный `CEH_MONITOR_BASE_URL`;
- backup/restore drill является частью CI;
- `Staging-приемка` выполняет точный backend release contract до smoke/load-test;
- нагрузочный сценарий по умолчанию dry-run.

## Документация

- `docs/FIRST_RUN.md` — первый локальный и production запуск;
- `docs/PRODUCTION.md` — production по IP + порт;
- `docs/GO_LIVE.md` — последовательность Gate и Go/No-Go;
- `docs/BACKUP.md` — backup/off-site/restore;
- `docs/RELEASE_CHECKLIST.md` — release checklist;
- `docs/STAGING_ACCEPTANCE.md` — staging acceptance;
- `docs/ANDROID_RELEASE.md` — подписанный Android release;
- `docs/INTEGRATION_UNF_CLOUD.md` — облачная УНФ;
- `docs/UNF_BRIDGE_RUNBOOK.md` — эксплуатация bridge.

Ruleset `Защита main` уже активен; изменения идут через pull request с двумя обязательными status checks. До фактического go-live остаются внешние шаги из issue #7 (реальный IP/порт, deployment, backup/monitoring, Android signing + physical UAT), issue #8 (реальный tenant УНФ) и административная косметика issue #12.
