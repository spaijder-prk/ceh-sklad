# Цех Склад

Монорепозиторий системы складского учета для нескольких складов и торговых представителей с Android-клиентом, web-панелью и интеграцией с **1С:Управление нашей фирмой (УНФ) в облаке**.

Текущая версия продукта: **0.4.0**.

## Что входит

- `backend/` — FastAPI + PostgreSQL, транзакционное складское ядро, задолженность, роли, аудит, 1С/УНФ API;
- `android/` — приложение торгового представителя с offline-кэшем, очередью неподтвержденных операций и realtime;
- `admin-web/` — панель администратора/руководителя;
- `unf-bridge/` — bridge к облачной УНФ/1С:Фреш;
- `docs/` — первый запуск, production, backup/restore, staging, release и интеграция;
- `scripts/` — deploy, backup/restore, monitoring, release-проверки и экспорт internal CA.

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

После запуска:

- web: `http://localhost:5173`;
- backend: `http://localhost:8000`;
- OpenAPI: `http://localhost:8000/docs`.

Development Compose публикует web/API только на `127.0.0.1`, PostgreSQL наружу не публикуется.

## Production без домена: публичный IP + нестандартный порт

Production может работать за NAT без свободных внешних TCP 80/443. Клиенты используют один origin:

```text
https://<PUBLIC_IP>:<HTTPS_PORT>
```

Пример сети:

```text
PUBLIC_IP:40022/TCP -> SERVER_LAN_IP:22      # SSH
PUBLIC_IP:40443/TCP -> SERVER_LAN_IP:40443  # HTTPS web/API/WSS
```

Внешние `80` и `443` проекту не нужны. TLS обслуживается внутренним CA Caddy (`tls internal`). После первого запуска его public root certificate устанавливается на доверенные компьютеры и Android-устройства.

Создать production env:

```bash
python3 scripts/prepare_production_env.py \
  --ip <REAL_PUBLIC_IP> \
  --port <REAL_HTTPS_PORT>
```

Перед запуском:

```bash
python3 scripts/deploy_production.py --check-only
```

Запуск:

```bash
python3 scripts/deploy_production.py
```

Экспорт публичного root CA:

```bash
python3 scripts/export_internal_ca.py
```

Проверка через CA выполняется без отключения TLS verification. Не используйте `curl -k`, `verify=false` или HTTP как production-обход.

PostgreSQL `5432` и FastAPI `8000` не должны быть доступны извне.

## Backup

Production DB backup:

```bash
./scripts/backup.sh --production
```

Internal Caddy PKI backup для disaster recovery:

```bash
sh scripts/backup_caddy_pki.sh
```

PKI archive содержит CA private key и является секретом. Подробности: `docs/BACKUP.md`.

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

## Web-панель без Docker

```bash
cd admin-web
npm ci
npm run dev
```

Production build требует явный HTTPS API URL:

```bash
VITE_API_BASE_URL=https://<PUBLIC_IP>:<HTTPS_PORT>/api/v1 npm run build
```

## Android

Debug использует emulator URL. Release требует production HTTPS origin:

```bash
./android/gradlew -p android :app:assembleRelease \
  -PCEH_API_BASE_URL=https://<PUBLIC_IP>:<HTTPS_PORT>/
```

Release Android запрещает cleartext HTTP. Для internal CA его release network-security config доверяет system CA и CA, установленным пользователем.

Перед Android production release:

1. экспортировать `ceh-sklad-root-ca.crt`;
2. установить его на контролируемое Android-устройство;
3. добавить base64 public root certificate в GitHub Secret `CEH_INTERNAL_CA_CERT_BASE64`;
4. настроить четыре Android signing secrets;
5. запустить `Подписанный Android release`.

Workflow сначала проверяет production backend через internal CA, точную версию и Alembic head; только затем использует keystore. GitHub Release содержит APK, AAB, manifest, root CA и `SHA256SUMS.txt`.

Подробности: `docs/ANDROID_RELEASE.md`.

## 1С:УНФ Cloud

Универсальный обмен находится под `/api/v1/integration/1c`. Реальный tenant подключается после серверной и Android-приёмки. Подробности: `docs/INTEGRATION_UNF_CLOUD.md`, `docs/UNF_BRIDGE_RUNBOOK.md`, `docs/UNF_TENANT_CHECKLIST.md`, issue #8.

## Безопасность

- роли `representative`, `admin`, `manager` проверяются сервером;
- пароли хэшируются Argon2;
- смена/reset пароля инвалидирует старые REST/WSS сессии;
- browser session использует `HttpOnly`, `SameSite=Strict` и CSRF;
- JWT не хранится в browser localStorage и не помещается в WebSocket query;
- backend container работает непривилегированным пользователем;
- release Android запрещает HTTP;
- Android Auto Backup отключён;
- production Caddy использует HTTPS и security headers;
- internal CA private key остаётся в persistent Caddy PKI и резервируется отдельно;
- PostgreSQL/FastAPI не публикуются напрямую наружу;
- signing keys, реальные env, DB/PKI backup и release artifacts исключены из Git.

## Эксплуатация

- `/health` — liveness + версия;
- `/health/ready` — PostgreSQL + Alembic revision + версия;
- `/api/v1/system/status` — admin/manager status;
- `production_monitor.py` поддерживает `CEH_MONITOR_CA_CERT`;
- staging и Android release используют `CEH_INTERNAL_CA_CERT_BASE64`;
- backup/restore drill является частью CI.

## Документация

- `docs/FIRST_RUN.md` — первый локальный и production запуск;
- `docs/PRODUCTION.md` — NAT/IP/нестандартный порт/internal CA;
- `docs/GO_LIVE.md` — Go/No-Go;
- `docs/BACKUP.md` — DB + Caddy PKI backup;
- `docs/ANDROID_RELEASE.md` — подписанный Android release;
- `docs/STAGING_ACCEPTANCE.md` — staging acceptance;
- `docs/INTEGRATION_UNF_CLOUD.md` — облачная УНФ.

Ruleset `Защита main` активен; изменения идут через PR с двумя обязательными status checks. До фактического go-live остаются внешние шаги issue #7, реальная УНФ issue #8 и административная уборка issue #12.
