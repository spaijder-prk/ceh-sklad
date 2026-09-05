# Release preflight staging

`release_preflight.py` — read-only gate перед staging smoke, нагрузочным прогоном и UAT. Он не создает складские документы, продажи и документы УНФ.

## Что проверяется

1. staging URL — только чистый HTTPS origin без credentials/path/query;
2. `GET /health/ready` — `status=ready`, `database=ok`, наличие Alembic revision;
3. при `--expected-schema-revision` — точное совпадение ожидаемой revision;
4. при наличии `CEH_STAGING_1C_KEY` или `CEH_1C_KEY` — профиль `unf-cloud-v2`, целевая конфигурация УНФ и `deployment=cloud`;
5. UNF outbox — число ready/blocked объектов и до пяти безопасных примеров blocking reasons;
6. в строгом режиме `--require-unf-ready` любой blocked outbox или отсутствие сервисного ключа делает preflight неуспешным.

Команда использует только `GET`. Сервисный ключ передается только в integration endpoints и не попадает в JSON-отчет.

## Локальный запуск

```bash
export CEH_STAGING_1C_KEY='***'
python scripts/release_preflight.py \
  --base-url 'https://staging-sklad.example.ru' \
  --expected-schema-revision '20260904_09' \
  --require-unf-ready \
  --output /tmp/ceh-release-preflight.json
```

Коды возврата:

- `0` — gate готов;
- `2` — некорректная локальная конфигурация запуска;
- `3` — staging доступен, но release prerequisites не выполнены или удаленная проверка завершилась ошибкой.

## GitHub Actions

Ручной workflow `Staging-приемка` запускает preflight до авторизации representative и до load-test. JSON сохраняется как artifact `staging-release-preflight`, в том числе при неуспешном gate.

`require_unf_ready=true` следует включать на финальном staging прогоне перед UAT/релизом. До получения реального tenant его можно оставить выключенным, если `CEH_STAGING_1C_KEY` еще не настроен.

## Связь с реальной 1С:Фреш

Этот preflight проверяет внешний `ceh-sklad` и серверный integration contract/outbox. Он **не заменяет** живую проверку tenant.

После получения URL и сервисной учетной записи УНФ обязательный второй gate:

```bash
ceh-unf-fresh-health --mapping /etc/ceh-sklad/unf-tenant.json
```

`ceh-unf-fresh-health` дополнительно проверяет реальный `$metadata`, tenant mapping, поля импорта, известные `Ref_Key` и собираемость payload всех ready операций без POST/create/confirm.
