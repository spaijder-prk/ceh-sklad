# Runbook bridge 1С:УНФ Cloud / 1С:Фреш

## Принцип безопасности

Bridge не получает учетные данные УНФ из Android/web. `UNF_FRESH_LOGIN`, `UNF_FRESH_PASSWORD` и `CEH_1C_KEY` передаются процессу только через secret storage/переменные окружения. Несекретный mapping хранит имена OData EntitySet/полей и Ref_Key согласованных справочников.

Запись по умолчанию выключена. Команда `ceh-unf-fresh-sync` без `--execute` выполняет только:

1. проверку профиля `unf-cloud-v2` у ceh-sklad;
2. чтение `$metadata` УНФ;
3. валидацию tenant mapping;
4. чтение `/unf/outbox`;
5. построение всех document payload в памяти.

Она не вызывает create/Post в УНФ и не выполняет confirm-export.

## 1. Получить metadata

```bash
export UNF_FRESH_LOGIN='service-user'
export UNF_FRESH_PASSWORD='***'
ceh-unf-fresh-probe \
  --url 'https://1cfresh.com/a/...' \
  --details \
  --all
```

Секреты в stdout не выводятся.

## 2. Заполнить mapping

Скопируйте `unf-bridge/unf-tenant.example.json` во внешний конфигурационный каталог и замените только значения `REPLACE_*` данными фактического tenant.

Обязательно сопоставляются:

- два разных вида цен: розничный и оптовый;
- организация;
- служебный покупатель розницы и правило покупателя опта;
- касса и статья ДДС;
- поля/табличные части пяти типов документов;
- для каждого склада представителя — отдельный `representative_payer_refs`, если кассовый документ требует плательщика/подотчетное лицо.

Пароли/токены в mapping не помещаются.

## 3. Dry-run

```bash
export CEH_API_URL='https://sklad.example.ru'
export CEH_1C_KEY='***'
export UNF_FRESH_LOGIN='service-user'
export UNF_FRESH_PASSWORD='***'

ceh-unf-fresh-sync --mapping /etc/ceh-sklad/unf-tenant.json --limit 20
```

Ожидаемый итог содержит `DRY-RUN`, количество ready/blocked и план документов. Любая ошибка `$metadata`, semantic aliases, отсутствующий Ref_Key товара/склада или legacy-продажа без типа цены должна быть устранена до записи.

## 4. Тестовая запись без проведения

Сначала оставьте в mapping:

```json
{"post_documents": false}
```

и выполните:

```bash
ceh-unf-fresh-sync --mapping /etc/ceh-sklad/unf-tenant.json --limit 1 --execute
```

Bridge сначала ищет документ по детерминированному external key. Если он уже существует после предыдущего сетевого разрыва, второй create не выполняется. `confirm-export` вызывается только после получения `Ref_Key` всех необходимых документов.

## 5. Проведение

Только после проверки тестовых документов и прав сервисного пользователя установите `post_documents=true` и повторите UAT. `Post()` выполняется после create. При mixed adjustment создаются два документа и затем один batch-confirm.

## 6. Аварийное правило

Если команда завершилась ошибкой после возможной записи в УНФ, **не создавайте документ вручную и не меняйте external key**. Повторите ту же операцию: find-before-create должен найти существующий документ и продолжить confirm без дубля.

При `BLOCKED` запись этой операции не выполняется. Код возврата 3 означает, что в outbox остались заблокированные элементы и требуется исправить mapping/справочники.
