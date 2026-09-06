# Release preflight staging

`release_preflight.py` — read-only gate перед staging smoke, нагрузочным прогоном и UAT. Он не создаёт складские документы, продажи или документы УНФ.

Production/staging endpoint может использовать внутренний CA Caddy и нестандартный порт, например `https://PUBLIC_IP:40443`.

## Доверие к internal CA

При ручном запуске сначала экспортируйте public root CA с production server и укажите его Python/HTTP-клиентам:

```bash
export SSL_CERT_FILE=/path/to/ceh-sklad-root-ca.crt
export REQUESTS_CA_BUNDLE=/path/to/ceh-sklad-root-ca.crt
```

Не используйте `-k`, `verify=false` или отключение TLS verification.

В GitHub workflow `Staging-приемка` эти переменные настраиваются автоматически из `CEH_INTERNAL_CA_CERT_BASE64`.

## Что проверяется

1. URL — чистый HTTPS origin без credentials/path/query;
2. `GET /health/ready` — `status=ready`, `database=ok`, Alembic revision;
3. при `--expected-schema-revision` — exact revision;
4. при наличии `CEH_STAGING_1C_KEY`/`CEH_1C_KEY` — профиль УНФ;
5. UNF outbox и blocking reasons;
6. при `--require-unf-ready` blocked outbox/нет ключа делают gate неуспешным.

Команда использует только GET. Сервисный ключ не записывается в JSON report.

## Локальный запуск

```bash
export SSL_CERT_FILE=/path/to/ceh-sklad-root-ca.crt
export REQUESTS_CA_BUNDLE=/path/to/ceh-sklad-root-ca.crt
export CEH_STAGING_1C_KEY='***'

python scripts/release_preflight.py \
  --base-url 'https://<PUBLIC_IP>:40443' \
  --expected-schema-revision '20260904_09' \
  --require-unf-ready \
  --output /tmp/ceh-release-preflight.json
```

Коды возврата:

- `0` — gate готов;
- `2` — некорректная локальная конфигурация;
- `3` — prerequisites не выполнены или удалённая проверка завершилась ошибкой.

## GitHub Actions

`Staging-приемка` до representative/login/load-test:

1. декодирует публичный internal root CA;
2. выполняет `scripts/verify_release_backend.py --ca-cert ...` для exact version/Alembic contract;
3. запускает `release_preflight.py` с тем же trust environment;
4. сохраняет JSON artifacts.

`require_unf_ready=true` включается на финальном прогоне перед УНФ UAT.

## Реальная 1С:Фреш

Этот preflight проверяет `ceh-sklad` и серверный integration contract/outbox, но не заменяет живую проверку tenant.

После получения реальной УНФ выполняется отдельный gate:

```bash
ceh-unf-fresh-health --mapping /etc/ceh-sklad/unf-tenant.json
```

Он проверяет реальный `$metadata`, mapping, reference objects и собираемость payload без массовой записи.
