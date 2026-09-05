# Цех Склад

Монорепозиторий системы складского учета для нескольких складов и торговых представителей с Android-клиентом, web-панелью и интеграцией с **1С:Управление нашей фирмой (УНФ) в облаке**.

## Что входит

- `backend/` — FastAPI + PostgreSQL, транзакционное складское ядро, задолженность, роли, аудит, 1С/УНФ API;
- `android/` — приложение торгового представителя с offline-кэшем, очередью неподтвержденных операций и realtime;
- `admin-web/` — панель администратора/руководителя;
- `unf-bridge/` — отдельный bridge к облачной УНФ/1С:Фреш с metadata-driven mapping, dry-run, health и идемпотентным экспортом;
- `docs/` — архитектура, production, backup/restore, staging и интеграция УНФ Cloud;
- `scripts/` — backup/restore, load-test и staging smoke.

## Основные правила учета

- проведенные документы не редактируются задним числом;
- исправления оформляются отдельной корректировкой;
- остаток изменяется только транзакционно вместе с документом и движениями;
- мобильная операция не уменьшает локальный остаток до подтверждения backend;
- повторная доставка защищена идемпотентным `operation_key`;
- розничная и оптовая цены хранятся отдельно;
- каждому торговому представителю соответствует виртуальный склад `ceh-sklad`.

## 1С:УНФ Cloud

Универсальный обмен находится под `/api/v1/integration/1c`. Для целевой конфигурации УНФ Cloud дополнительно реализованы:

- `GET /api/v1/integration/1c/unf/profile` — версия/профиль контракта;
- `GET /api/v1/integration/1c/unf/outbox` — неподтвержденные операции с готовым сопоставлением документов УНФ;
- `POST /api/v1/integration/1c/confirm-export` и batch-вариант — идемпотентное подтверждение после фактической записи документа в УНФ.

Базовое сопоставление:

- перемещения, выдача и возврат → `Перемещение запасов`;
- продажа → `Расходная накладная`;
- сдача выручки → `Поступление в кассу`;
- положительная корректировка → `Оприходование запасов`;
- отрицательная → `Списание запасов`;
- смешанная корректировка помечается `requires_split=true` и разбивается bridge на два документа.

Учетные данные облачной УНФ не хранятся в Android/web. Между `ceh-sklad` и конкретным облачным tenant используется `unf-bridge`. Для 1С:Фреш он получает фактические EntitySet/поля из `$metadata`, а не зашивает имена объектов конкретной версии УНФ.

Безопасный порядок discovery/UAT:

```bash
# 1. Один read-only discovery с сервисными credentials из secret storage.
ceh-unf-fresh-probe \
  --url 'https://1cfresh.com/a/...' \
  --details --all \
  --snapshot /var/lib/ceh-unf/unf-metadata.json

# 2. После заполнения non-secret mapping — offline-сверка без сети/credentials.
ceh-unf-metadata-validate \
  --mapping /etc/ceh-sklad/unf-tenant.json \
  --snapshot /var/lib/ceh-unf/unf-metadata.json

# 3. Статический бизнес-аудит mapping.
ceh-unf-tenant-audit --mapping /etc/ceh-sklad/unf-tenant.json

# 4. Перед записью — живая read-only проверка текущего tenant/backend/outbox.
ceh-unf-fresh-health --mapping /etc/ceh-sklad/unf-tenant.json --limit 100
```

Metadata snapshot не содержит логин, пароль или Authorization headers, но раскрывает URL/структуру tenant и поэтому хранится как внутренний UAT artifact. Offline-validator возвращает SHA-256 exact snapshot и mapping; эти digest фиксируются в release record. Tenant-specific касса, статья ДДС, payer и другие обязательные справочники проверяются через конфигурируемые `reference_checks` без изменения bridge-кода.

Подробности: `docs/INTEGRATION_UNF_CLOUD.md`, `docs/UNF_BRIDGE_RUNBOOK.md`, `docs/UNF_TENANT_CHECKLIST.md`. Реальное подключение tenant отслеживается в issue #8.

## Быстрый локальный запуск

Создайте `.env` на основе `.env.example`, затем:

```bash
docker compose up --build
```

После запуска:

- backend: `http://localhost:8000`;
- OpenAPI: `http://localhost:8000/docs`;
- web: `http://localhost:5173` при отдельном запуске Vite.

Структура БД создается/обновляется только Alembic-миграциями.

## Backend без Docker

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
uvicorn app.main:app --reload
```

Тесты требуют PostgreSQL и выполняются командой:

```bash
pytest -q
```

## Web-панель

```bash
cd admin-web
npm install
npm run dev
```

Production build требует явный HTTPS URL:

```bash
VITE_API_BASE_URL=https://sklad.example.ru/api/v1 npm run build
```

CI дополнительно проверяет, что `localhost:8000` не попал в production bundle.

## Android

Debug использует локальный emulator URL. Release требует production HTTPS API:

```bash
gradle -p android :app:assembleRelease -PCEH_API_BASE_URL=https://sklad.example.ru/
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

## Безопасность

- роли `representative`, `admin`, `manager` проверяются сервером;
- пароли хэшируются Argon2;
- JWT содержит отпечаток текущего password hash, поэтому смена/reset пароля инвалидирует старые REST/WSS сессии;
- после пяти неверных паролей вход блокируется на пять минут в PostgreSQL;
- production secrets имеют серверную валидацию;
- backend Docker image работает от непривилегированного пользователя;
- production Caddy включает TLS/security headers;
- PostgreSQL и FastAPI не публикуются напрямую наружу в production Compose.

## Эксплуатация

- `/health` — liveness;
- `/health/ready` — PostgreSQL + текущая Alembic revision;
- `/api/v1/system/status` — admin/manager: очередь обмена, ошибки 1С, временно заблокированные аккаунты и готовность сопоставлений УНФ;
- backup/restore drill является частью CI;
- `Staging-приемка` умеет read-only проверку УНФ Cloud и строгий `require_unf_ready`;
- нагрузочный сценарий по умолчанию dry-run; реальные продажи требуют отдельного флага подтверждения;
- Android emulator smoke автоматически запускается только для последнего Android/workflow commit, а main CI не тратит Android build на чистые bridge/docs-коммиты в PR.

## Production

См.:

- `docs/PRODUCTION.md`;
- `docs/RELEASE_CHECKLIST.md`;
- `docs/STAGING_ACCEPTANCE.md`;
- `docs/INTEGRATION_UNF_CLOUD.md`;
- `docs/UNF_BRIDGE_RUNBOOK.md`.

Основная разработка теперь ведётся из `main`; ранее разошедшиеся истории `main` и `feature/bazovoe-yadro` консолидированы merge-коммитом `57826395b27e29928ebcd8aeccdf9a1c5afb5fd5` без потери истории. До фактического production-релиза остаются внешние шаги из issues #7 и #8: реальный HTTPS deployment, подписанный Android release/проверка на физическом устройстве и UAT с настоящим tenant УНФ.
