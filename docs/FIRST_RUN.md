# Первый запуск Цех Склад

Этот документ разделяет **локальный первый запуск** и **первый production-запуск**. Не используйте development Compose как замену production-контуру.

## 1. Локальный первый запуск

### Требования

- Docker Engine;
- Docker Compose v2;
- Git;
- `make` — необязательно, все команды можно выполнить напрямую через `docker compose`.

### Подготовка

```bash
cp .env.example .env
```

`.env` предназначен только для локальной разработки и игнорируется Git. Даже локальные реальные пароли, токены, tenant-параметры и signing material не коммитьте.

### Запуск всего минимального контура

```bash
make first-run
```

Эквивалент без `make`:

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Локальный Compose поднимает:

- PostgreSQL;
- FastAPI backend с автоматическим `alembic upgrade head`;
- web-панель через Vite development server.

Порты публикуются только на loopback-интерфейс хоста:

- web: `http://localhost:5173`;
- API: `http://localhost:8000`;
- OpenAPI: `http://localhost:8000/docs`.

PostgreSQL наружу не публикуется.

### Минимальная проверка

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/health/ready
```

Затем откройте `http://localhost:5173`, войдите локальным bootstrap-администратором из `.env` и проверьте, что панель открывается без ошибок.

Для стандартного `.env.example` логин — `admin`. Пароль из примера допустим только для изолированного локального контура; не переносите его в production.

### Логи и состояние

```bash
make status
make logs
```

Остановка без удаления данных:

```bash
make down
```

Полный сброс **только локальной development-БД**:

```bash
docker compose down -v
```

Команда удалит локальный volume PostgreSQL. На production её применять нельзя.

## 2. Перед первым production-запуском

Production разрешён только после выполнения Gate 0 из `docs/GO_LIVE.md`: repository ruleset `Защита main` должен быть Active, а обязательные CI checks — зелёными.

Нужны:

- отдельный production host;
- рабочий DNS-домен, направленный на него;
- Docker Engine и Docker Compose v2;
- корректное системное время/NTP;
- наружу открыты только необходимые 80/443;
- PostgreSQL 5432 и backend 8000 не опубликованы в интернет;
- менеджер секретов или другое защищённое место для production credentials.

### Создать production env

На production host из проверенного release commit:

```bash
python scripts/prepare_production_env.py \
  --domain <REAL_DOMAIN> \
  --email <REAL_ACME_EMAIL>
```

Не копируйте `.env.production` в Git, issue, PR, чат или логи. На POSIX-файловой системе файл должен иметь права `0600`.

### Обязательный read-only preflight

До изменения контейнеров и данных:

```bash
python scripts/deploy_production.py --check-only
```

Preflight проверяет production env, его права, Docker daemon/Compose, итоговую Compose-конфигурацию и DNS рабочего домена.

### Первый deployment

Только после успешного preflight:

```bash
python scripts/deploy_production.py
```

На первом запуске рабочей БД ещё нет, поэтому предварительный backup не требуется. При последующих обновлениях deploy-скрипт создаёт backup работающей БД перед изменением контура, если явно не указан опасный `--skip-backup`.

### Проверка после deployment

```bash
curl --fail https://<REAL_DOMAIN>/health
curl --fail https://<REAL_DOMAIN>/health/ready
```

Также обязательно проверить:

1. TLS-сертификат и HTTPS web-панель;
2. что 5432 и 8000 недоступны извне;
3. вход bootstrap-администратора и немедленную смену временного пароля;
4. повторный вход уже с новым паролем;
5. удалить из `.env.production` обе строки `BOOTSTRAP_ADMIN_LOGIN` и `BOOTSTRAP_ADMIN_PASSWORD`, затем повторно выполнить `python scripts/deploy_production.py --skip-backup --no-build` и убедиться, что новый вход по-прежнему работает;
6. создание/проверку ролей `representative`, `admin`, `manager`;
7. production WebSocket через `wss://`;
8. backup, off-site backup и restore drill по `docs/BACKUP.md`;
9. мониторинг и systemd timers;
10. подписанный Android release и physical-device UAT.

Удаление `BOOTSTRAP_ADMIN_*` после подтверждённой смены пароля отключает механизм создания первого администратора. Существующий пользователь остаётся в PostgreSQL и продолжает работать с новым паролем. Не удаляйте эти строки до успешного первого входа и проверки нового пароля.

## 3. Что не включать на первом старте

Не включайте регулярный обмен с реальной облачной 1С:УНФ до завершения physical-device UAT и controlled tenant audit. Первое подключение УНФ выполняется по `docs/INTEGRATION_UNF_CLOUD.md`, `docs/UNF_TENANT_CHECKLIST.md` и issue #8.

Не создавайте production Android signing key внутри репозитория. Используйте `scripts/prepare_android_signing.py`: скрипт специально запрещает размещение signing material внутри Git working tree.

## 4. Критерий готовности к реальным данным

Перед загрузкой реальных хозяйственных данных одновременно должны быть выполнены:

- активна защита `main`;
- release commit имеет зелёные обязательные CI checks;
- production HTTPS health/readiness зелёные;
- bootstrap-пароль сменён и повторный вход новым паролем подтверждён;
- `BOOTSTRAP_ADMIN_LOGIN`/`BOOTSTRAP_ADMIN_PASSWORD` удалены из production env, bootstrap отключён;
- внешний доступ ограничен 80/443;
- backup + off-site + restore drill проверены;
- monitoring активен;
- подписанный Android APK проверен по checksum/signing certificate;
- physical-device UAT не выявил потери или дублирования остатков, продаж и денежных операций.

Полный Go/No-Go порядок находится в `docs/GO_LIVE.md`.
