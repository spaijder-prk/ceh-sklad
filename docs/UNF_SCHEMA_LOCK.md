# Schema lock для 1С:УНФ

Bridge `0.9.0+` защищает автоматический обмен с облачной УНФ от незаметного изменения опубликованной OData-схемы. Начиная с `0.9.1`, один и тот же lock применяется и к исходящим документам, и к входящему импорту номенклатуры/цен/складов.

## Как зафиксировать схему

1. Получите свежий snapshot:

```bash
ceh-unf-fresh-probe \
  --url 'https://1cfresh.com/a/...' \
  --details --all \
  --snapshot /var/lib/ceh-unf/unf-metadata.json
```

2. Проверьте заполненный mapping offline:

```bash
ceh-unf-metadata-validate \
  --mapping /etc/ceh-sklad/unf-tenant.json \
  --snapshot /var/lib/ceh-unf/unf-metadata.json
```

3. Из успешного JSON скопируйте `metadata_structure_sha256` в несекретный mapping:

```json
{
  "expected_metadata_structure_sha256": "64_hex_символа"
}
```

4. Повторите offline validation и затем `ceh-unf-fresh-health`. Оба должны показать совпадение схемы.

## Fail-safe поведение

- пустое `expected_metadata_structure_sha256` допускается для discovery и dry-run;
- `ceh-unf-fresh-sync --execute` без schema lock завершается до записи документа УНФ;
- `ceh-unf-fresh-import-products --execute` и `ceh-unf-fresh-import-locations --execute` без schema lock завершаются до записи в `ceh-sklad`;
- если schema lock задан, но текущая `$metadata` имеет другой канонический digest, блокируются и dry-run, и execute;
- `ceh-unf-fresh-health` при drift возвращает `status=degraded` и `metadata_structure_matches_expected=false`;
- offline validator блокирует mapping, если зафиксированный lock не соответствует snapshot;
- ошибки lock/mapping завершаются как `CONFIG_ERROR` с кодом `2`, а не как retryable network failure;
- изменение пробелов/форматирования snapshot JSON не меняет `metadata_structure_sha256`: digest считается по канонической структуре EntitySet, полей и navigation.

## После обновления УНФ

Не заменяйте lock автоматически. При несовпадении:

1. остановите writer/import timers;
2. снимите новый metadata snapshot;
3. сравните структуру и повторите tenant mapping review;
4. выполните offline validation, tenant audit и live health;
5. при необходимости обновите mapping полей/EntitySet;
6. зафиксируйте новый `metadata_structure_sha256` в UAT/release record;
7. только после повторного dry-run/UAT обновите schema lock и верните автоматический обмен.

Lock не является секретом. Credentials, токены и пароли по-прежнему хранятся только во внешнем secret storage.
