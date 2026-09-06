# Цех Склад

Монорепозиторий системы складского учета для нескольких складов и торговых представителей с Android-клиентом, web-панелью и интеграцией с **1С:Управление нашей фирмой (УНФ) в облаке**.

Текущая версия продукта: **0.4.0**.

## Что входит

- `backend/` — FastAPI + PostgreSQL, транзакционное складское ядро, задолженность, роли, аудит, 1С/УНФ API;
- `android/` — приложение торгового представителя с offline-кэшем, очередью неподтвержденных операций и realtime;
- `admin-web/` — панель администратора/руководителя;
- `unf-bridge/` — отдельный bridge к облачной УНФ/1С:Фреш с metadata-driven mapping, dry-run, health и идемпотентным экспортом;
- `docs/` — архитектура, первый запуск, production, backup/restore, staging и интеграция УНФ Cloud;
- `scripts/` — production deploy, backup/restore, load-test, staging smoke и release-проверки.

## Основные правила учета

- проведенные документы не редактируются задним числом;
- исправления оформляются отдельной корректировкой;
- остаток изменяется только транзакционно вместе с документом и движениями;
- мобильная операция не уменьшает локальный остаток до подтверждения backend;
- повторная доставка защищена идемпотентным `operation_key`;
- розничная и оптовая цены хранятся отдельно;
- каждому торговому представителю соответствует виртуальный склад `ceh-sklad`.

## Первый локальный запуск

Подробный сценарий находится в `docs/FIRST_RUN.md`.

Создайте локальный `.env`:

```bash
cp .env.example .env
```

Затем поднимите весь минимальный контур одной командой:

```bash
make first-run
```

Без `make`:

```bash
docker compose config --quiet
docker compose up --build -d
```

После запуска:

- web-панель: `http://localhost:5173`;
- backend: `http://localhost:8000`;
- OpenAPI: `http://localhost:8000/docs`.

Development Compose публикует web/API только на `127.0.0.1`, PostgreSQL наружу не публикуется. Backend при старте автоматически выполняет `alembic upgrade head`.

Проверка:

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/health/ready
```

## Production

Production-порядок задают `docs/FIRST_RUN.md`, `docs/PRODUCTION.md` и `docs/GO_LIVE.md`.

Сначала безопасно создайте `.env.production`:

```bash
python scripts/prepare_production_env.py \
  --domain sklad.example.ru \
  --email admin@example.ru
```

До любых изменений контейнеров выполните read-only preflight:

```bash
python scripts/deploy_production.py --check-only
```

После настройки DNS, проверки Gate 0 и открытия 80/443 production можно поднять командой:

```bash
python scripts/deploy_production.py
```

Скрипт проверяет права `.env.production`, валидирует Docker Compose и DNS, перед обновлением уже работающей БД делает production backup, запускает/обновляет контейнеры и ждёт внешнего HTTPS `/health` + `/health/ready` с версией из `VERSION`.

Ручные команды остаются доступны и описаны в `docs/PRODUCTION.md`. Production backup/restore выполняются только с явным флагом:

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

Тесты требуют PostgreSQL и выполняются командой:

```bash
pytest -q
```

## Web-панель без Docker

```bash
cd admin-web
npm ci
npm run dev
```

Production build требует явный HTTPS URL:

```bash
VITE_API_BASE_URL=https://sklad.example.ru/api/v1 npm run build
```

CI дополнительно проверяет, что `localhost:8000` не попал в production bundle.

## Android

Debug использует локальный emulator URL. Release требует production HTTPS API и собирается только через зафиксированный Gradle Wrapper:

```bash
./android/gradlew -p android :app:assembleRelease \
  -PCEH_API_BASE_URL=https://sklad.example.ru/
```

Release signing читается только из внешних секретов/переменных. Keystore не хранится в репозитории. Подробности — `docs/ANDROID_RELEASE.md`.

Android поддерживает:

- вход только торгового представителя с привязанным виртуальным складом;
- остатки обычных складов и собственный остаток;
- корзину из нескольких товаров и розничную/оптовую цену;
- продажу, возврат и сдачу денег;
- долг и собственную историю;
- Room-кэш подтвержденных данных;
- Room/WorkManager очередь операций при отсутствии сети;
- WebSocket с переподключением;
- защищенную сессию через Android Keystore;
- смену собственного пароля;
- нейтральную обработку 401 и точный `Retry-After` при временной блокировке входа.

## 1С:УНФ Cloud

Универсальный обмен находится под `/api/v1/integration/1c`. Для целевой конфигурации УНФ Cloud дополнительно реализованы профиль, outbox и идемпотентное подтверждение экспорта. Учетные данные облачной УНФ не хранятся в Android/web; между `ceh-sklad` и конкретным облачным tenant используется `unf-bridge`.

Подробности: `docs/INTEGRATION_UNF_CLOUD.md`, `docs/UNF_BRIDGE_RUNBOOK.md`, `docs/UNF_TENANT_CHECKLIST.md`. Реальное подключение tenant отслеживается в issue #8.

## Безопасность

- роли `representative`, `admin`, `manager` проверяются сервером;
- пароли хэшируются Argon2;
- JWT содержит отпечаток текущего password hash, поэтому смена/reset пароля инвалидирует старые REST/WSS сессии;
- после пяти неверных паролей вход блокируется на пять минут в PostgreSQL;
- production secrets имеют серверную валидацию;
- browser cookie-сессия защищена `HttpOnly`, `SameSite=Strict` и CSRF-проверкой;
- backend Docker image работает от непривилегированного пользователя;
- production Caddy включает TLS/security headers;
- PostgreSQL и FastAPI не публикуются напрямую наружу в production Compose;
- development Compose публикует web/API только на loopback хоста;
- signing keys, реальные env, backup, отчеты и release-артефакты исключены из Git.

## Эксплуатация

- `/health` — liveness + версия продукта;
- `/health/ready` — PostgreSQL + текущая Alembic revision + версия продукта;
- `/api/v1/system/status` — admin/manager: очередь обмена, ошибки 1С, временно заблокированные аккаунты и готовность сопоставлений УНФ;
- backup/restore drill является частью CI;
- `Staging-приемка` умеет read-only проверку УНФ Cloud и строгий `require_unf_ready`;
- нагрузочный сценарий по умолчанию dry-run; реальные продажи требуют отдельного флага подтверждения.

## Документация запуска и эксплуатации

- `docs/FIRST_RUN.md` — первый локальный и production-запуск;
- `docs/GO_LIVE.md` — последовательность Gate и Go/No-Go;
- `docs/PRODUCTION.md` — production deployment;
- `docs/BACKUP.md` — backup/off-site/restore;
- `docs/RELEASE_CHECKLIST.md` — release checklist;
- `docs/STAGING_ACCEPTANCE.md` — staging acceptance;
- `docs/INTEGRATION_UNF_CLOUD.md` — интеграция с облачной УНФ;
- `docs/UNF_BRIDGE_RUNBOOK.md` — эксплуатация bridge.

Изменения должны попадать в `main` через pull request после активации repository ruleset. До фактического production-релиза остаются внешние шаги из issues #7, #8 и #10: активировать защиту `main`, выполнить реальный HTTPS deployment, создать подписанный Android release/проверить его на физическом устройстве и пройти UAT с настоящим tenant УНФ.
