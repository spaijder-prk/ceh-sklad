# Приемка staging

Ручной workflow `Staging-приемка` предназначен для проверки уже развернутого HTTPS staging-окружения. По умолчанию он не создает складских или денежных документов.

## GitHub Secrets

В Actions необходимо задать:

- `CEH_STAGING_REP_LOGIN` — логин отдельного тестового торгового представителя;
- `CEH_STAGING_REP_PASSWORD` — его пароль;
- `CEH_STAGING_1C_KEY` — сервисный ключ тестового контура 1С; необязателен для остальных проверок.

Не используйте production-пароли для staging-приемки.

## Входные параметры workflow

- `base_url` — HTTPS origin staging;
- `location_id` — виртуальный склад тестового представителя;
- `product_id` — товар с известным достаточным остатком;
- `requests`, `concurrency`, `quantity` — параметры load-test;
- `execute_sales=false` — безопасное значение по умолчанию.

## Что проверяется без изменения данных

1. `GET /health/ready`: доступ к PostgreSQL и Alembic revision;
2. вход тестового представителя и соответствие его виртуального склада;
3. чтение собственного остатка, долга и истории;
4. WSS handshake `/api/v1/realtime`;
5. при наличии `CEH_STAGING_1C_KEY` — read-only запрос outbox 1С;
6. dry-run `scripts/load_test.py`, включая проверку достаточности остатка.

## Реальные тестовые продажи

Только при ручном выборе `execute_sales=true` workflow запускает load-test с защитной переменной `CEH_LOAD_TEST_CONFIRM`. Каждая продажа получает уникальный `operation_key`, а повтор первой операции проверяет идемпотентность.

После такого прогона тестовые продажи нужно учитывать как реальные документы staging и при необходимости закрыть их корректирующими документами, а не редактировать историю напрямую.

## Что сохранить в релизном журнале

- URL staging и дата прогона;
- номер GitHub Actions run;
- Alembic revision;
- количество запросов и concurrency;
- success/error count, throughput, p50/p95/max;
- результат проверки WSS и 1С;
- идентификатор подписанного Android artifact после отдельного release workflow;
- результат приемки в тестовой базе 1С.
