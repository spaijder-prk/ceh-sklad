# Первый запуск Цех Склад

Этот документ разделяет **локальный первый запуск** и **первый production-запуск**. Не используйте development Compose как замену production-контуру.

## 1. Локальный первый запуск

### Требования

- Docker Engine;
- Docker Compose v2;
- Git;
- `make` — необязательно.

### Подготовка и запуск

```bash
cp .env.example .env
make first-run
```

Без `make`:

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Локально доступны:

- web: `http://localhost:5173`;
- API: `http://localhost:8000`;
- OpenAPI: `http://localhost:8000/docs`.

PostgreSQL наружу не публикуется. Development web/API привязаны только к loopback.

Проверка:

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/health/ready
```

Для стандартного `.env.example` логин — `admin`. Локальные тестовые credentials нельзя переносить в production.

Остановка без удаления данных:

```bash
make down
```

Полный сброс **только локальной development-БД**:

```bash
docker compose down -v
```

## 2. Перед первым production-запуском

Gate 0 из `docs/GO_LIVE.md` должен быть пройден: `main` protected, ruleset `Защита main` Active, обязательные CI checks зелёные.

Production работает **без домена**. Нужны:

- отдельный production host;
- стабильный публичный IPv4/IPv6;
- выбранный внешний HTTPS-порт приложения;
- Docker Engine и Docker Compose v2;
- корректное системное время/NTP;
- входящий TCP `80` до Caddy для Let’s Encrypt ACME HTTP-01;
- входящий выбранный HTTPS-порт;
- PostgreSQL `5432` и backend `8000` закрыты извне;
- защищённое место для production credentials.

Let’s Encrypt выдаёт сертификат непосредственно на публичный IP. Такой сертификат короткоживущий, поэтому TCP `80` должен оставаться доступным для автоматического продления Caddy.

Если IP приватный или TCP `80` невозможно открыть/пробросить, этот профиль запускать нельзя. Не переключайтесь на HTTP; для такого окружения нужен отдельный внутренний CA/pinning режим.

### Создать production env

На production host из проверенного release commit:

```bash
python scripts/prepare_production_env.py \
  --ip <REAL_PUBLIC_IP> \
  --port <REAL_HTTPS_PORT> \
  --email <REAL_ACME_EMAIL>
```

Скрипт создаёт согласованные `CEH_PUBLIC_IP`, `CEH_PUBLIC_HOST`, `CEH_PUBLIC_PORT`, `CEH_PUBLIC_ORIGIN` и `CEH_PUBLIC_WS_ORIGIN`. Не редактируйте origin отдельно от IP/порта без необходимости: deploy preflight проверяет точное совпадение.

Не копируйте `.env.production` в Git, issue, PR, чат или логи. На POSIX-файловой системе файл должен иметь права `0600`.

### Обязательный read-only preflight

```bash
python scripts/deploy_production.py --check-only
```

Preflight проверяет production env, права файла, публичность IP, согласованность IP/port/origin, Docker daemon/Compose и итоговую Compose-конфигурацию. Внешнюю доступность TCP `80` проверьте с другой сети.

### Первый deployment

```bash
python scripts/deploy_production.py
```

На первом запуске рабочей БД ещё нет, поэтому предварительный backup не требуется. При последующих обновлениях deploy-скрипт создаёт backup работающей БД перед изменением контура, если явно не указан опасный `--skip-backup`.

### Проверка после deployment

```bash
curl --fail https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/health
curl --fail https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/health/ready
```

Если внешний порт `443`, `:443` можно не писать.

Также обязательно проверить:

1. TLS-сертификат публично доверен и SAN содержит фактический IP;
2. web-панель открывается через точный `https://IP:PORT`;
3. `5432` и `8000` недоступны извне;
4. вход bootstrap-администратора и немедленную смену временного пароля;
5. повторный вход уже с новым паролем;
6. удалить из `.env.production` обе строки `BOOTSTRAP_ADMIN_LOGIN` и `BOOTSTRAP_ADMIN_PASSWORD`, затем выполнить `python scripts/deploy_production.py --skip-backup --no-build`;
7. роли `representative`, `admin`, `manager`;
8. production WebSocket `wss://IP:PORT/api/v1/realtime` без JWT в URL;
9. backup, off-site backup и restore drill по `docs/BACKUP.md`;
10. monitoring/systemd timers;
11. подписанный Android release и physical-device UAT.

Удаление `BOOTSTRAP_ADMIN_*` после подтверждённой смены пароля отключает механизм создания первого администратора. Существующий пользователь остаётся в PostgreSQL. В критерии допуска обе переменные должны быть удалены из production env, bootstrap отключён.

## 3. Что не включать на первом старте

Не включайте регулярный обмен с реальной облачной 1С:УНФ до завершения physical-device UAT и controlled tenant audit. Первое подключение УНФ выполняется по `docs/INTEGRATION_UNF_CLOUD.md`, `docs/UNF_TENANT_CHECKLIST.md` и issue #8.

Не создавайте production Android signing key внутри репозитория. Используйте `scripts/prepare_android_signing.py`: helper запрещает размещение signing material внутри Git working tree.

## 4. Критерий готовности к реальным данным

Перед загрузкой реальных хозяйственных данных одновременно должны быть выполнены:

- активна защита `main`;
- release commit имеет зелёные обязательные CI checks;
- production HTTPS `https://IP:PORT/health` и `/health/ready` зелёные;
- публичный IP-сертификат валиден, автоматическое ACME renewal возможно через TCP `80`;
- bootstrap-пароль сменён и повторный вход новым паролем подтверждён;
- `BOOTSTRAP_ADMIN_LOGIN`/`BOOTSTRAP_ADMIN_PASSWORD` удалены из production env, bootstrap отключён;
- наружу доступны только TCP `80` для ACME и согласованный HTTPS-порт приложения (плюс его UDP при HTTP/3);
- `5432` и `8000` закрыты извне;
- backup + off-site + restore drill проверены;
- monitoring активен;
- подписанный Android APK проверен по checksum/signing certificate и содержит точный `https://IP:PORT/`;
- physical-device UAT не выявил потери или дублирования остатков, продаж и денежных операций.

Полный Go/No-Go порядок находится в `docs/GO_LIVE.md`.
