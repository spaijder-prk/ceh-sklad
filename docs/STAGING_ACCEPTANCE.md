# Приемка staging / production-кандидата

Ручной workflow `Staging-приемка` предназначен для проверки уже развернутого HTTPS endpoint по `IP:PORT`. По умолчанию он не создаёт складских или денежных документов.

## GitHub Secrets

В Actions необходимо задать:

- `CEH_INTERNAL_CA_CERT_BASE64` — base64 публичного `ceh-sklad-root-ca.crt`;
- `CEH_STAGING_REP_LOGIN` — логин отдельного тестового торгового представителя;
- `CEH_STAGING_REP_PASSWORD` — его пароль;
- `CEH_STAGING_1C_KEY` — сервисный ключ тестового контура `ceh-sklad` ↔ bridge УНФ; необязателен до строгого УНФ gate.

`CEH_INTERNAL_CA_CERT_BASE64` не содержит private key. Caddy CA private key в GitHub не загружается.

Учетные данные самой облачной УНФ не должны попадать в эти переменные, Android или web.

## Входные параметры

- `base_url` — точный HTTPS origin, например `https://PUBLIC_IP:40443`;
- `location_id` — виртуальный склад тестового представителя;
- `product_id` — товар с достаточным тестовым остатком;
- `requests`, `concurrency`, `quantity` — load-test;
- `require_unf_ready=false` — диагностический режим УНФ;
- `execute_sales=false` — безопасное значение по умолчанию.

## Как workflow доверяет HTTPS

Перед обращением к backend workflow:

1. декодирует `CEH_INTERNAL_CA_CERT_BASE64` во временный PEM/CRT;
2. проверяет сертификат через `openssl x509`;
3. задаёт `SSL_CERT_FILE` и `REQUESTS_CA_BUNDLE`;
4. передаёт CA явно в `scripts/verify_release_backend.py --ca-cert`;
5. удаляет временный root CA через `always()`.

TLS verification не отключается.

## Что проверяется без изменения данных

1. exact backend contract: HTTPS, `status=ready`, `database=ok`, версия и Alembic head;
2. release preflight;
3. вход тестового представителя;
4. соответствие его виртуального склада;
5. чтение собственного остатка, долга и истории;
6. WSS handshake `/api/v1/realtime` с JWT в `Authorization`, а не URL;
7. при наличии `CEH_STAGING_1C_KEY` — профиль и outbox УНФ;
8. dry-run `scripts/load_test.py`.

## Строгая готовность УНФ

Перед промышленным UAT повторите workflow с `require_unf_ready=true`. Тогда blocked outbox или отсутствие необходимых сопоставлений завершат приёмку ошибкой.

## Реальные тестовые продажи

Только при ручном `execute_sales=true` load-test получает защитное подтверждение и создаёт реальные тестовые продажи. Каждая операция имеет уникальный `operation_key`; повтор первой операции проверяет идемпотентность.

Тестовые документы затем исправляются отдельными корректирующими документами, а не редактированием истории.

## UAT с облачной УНФ

После read-only smoke проверить на реальной тестовой базе УНФ:

1. выдача представителю;
2. продажа retail;
3. продажа wholesale;
4. возврат;
5. сдача денег;
6. смешанная корректировка;
7. повторная доставка без дубля;
8. восстановление после разрыва между create и confirm;
9. итоговую сверку остатков.

## Что сохранить в релизном журнале

- production/staging `IP:PORT` без секретов;
- SHA-256 fingerprint internal root CA;
- GitHub Actions run;
- release commit SHA;
- Alembic revision/version;
- результат backend contract/preflight;
- WSS result;
- load-test success/error count, throughput, p50/p95/max;
- результаты controlled УНФ UAT;
- идентификатор подписанного Android Release.
