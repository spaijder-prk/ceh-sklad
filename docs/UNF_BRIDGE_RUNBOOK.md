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
  --all \
  --snapshot /var/lib/ceh-unf/unf-metadata.json
```

Секреты в stdout и snapshot не выводятся. Snapshot содержит полный список EntitySet, EDM-поля, `nullable`, navigation и связанные EntitySet/возможные табличные части. Он предназначен для внутреннего discovery/UAT и ревью mapping без повторного сетевого доступа к 1С.

Snapshot не содержит логин, пароль или Authorization headers, но раскрывает URL и структуру конкретного tenant. Не коммитьте production snapshot в публичный репозиторий.

## 2. Заполнить и проверить mapping offline

Скопируйте `unf-bridge/unf-tenant.example.json` во внешний конфигурационный каталог и замените только значения `REPLACE_*` данными фактического tenant или сохраненного metadata snapshot.

Обязательно сопоставляются:

- два разных вида цен: розничный и оптовый;
- организация;
- служебный покупатель розницы и правило покупателя опта;
- касса и статья ДДС;
- поля/табличные части пяти типов документов;
- для каждого склада представителя — отдельный `representative_payer_refs`, если кассовый документ требует плательщика/подотчетное лицо;
- `reference_checks` для tenant-specific справочников, которые должны существовать до запуска записи.

Пароли/токены в mapping не помещаются.

До повторного доступа к 1С mapping можно полностью сверить со snapshot локально:

```bash
ceh-unf-metadata-validate \
  --mapping /etc/ceh-sklad/unf-tenant.json \
  --snapshot /var/lib/ceh-unf/unf-metadata.json
```

Команда не использует сеть или credentials. Она проверяет совпадение `application_url`, наличие всех EntitySet, полей устойчивых ключей, price paths, payload schemas/табличных частей и EntitySet из `reference_checks`. Успех возвращает JSON `status=ready`; ошибка — `status=blocked` и код `3`.

Отдельно выполните статический бизнес-аудит mapping:

```bash
ceh-unf-tenant-audit --mapping /etc/ceh-sklad/unf-tenant.json
```

После offline-проверок повторная живая сверка остается обязательной перед UAT:

```bash
ceh-unf-fresh-probe \
  --url 'https://1cfresh.com/a/...' \
  --mapping /etc/ceh-sklad/unf-tenant.json
```

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

## 7. Read-only health

Для мониторинга используется отдельная команда, которая не вызывает create/Post/confirm:

```bash
ceh-unf-fresh-health --mapping /etc/ceh-sklad/unf-tenant.json --limit 100
```

Успешный stdout — одна JSON-строка с `status`, версией контракта, количеством опубликованных EntitySet, ready/blocked outbox и числом планируемых документов. `status=degraded` означает наличие заблокированных outbox элементов или отсутствующих обязательных reference objects и завершает команду кодом 3.

Коды процесса bridge:

- `0` — успешно;
- `2` — постоянная/ручная ошибка: права, неверный mapping, 4xx уровня 401/403/409/422 и т.п.;
- `3` — offline audit/metadata validation или health/outbox заблокирован;
- `75` — временная ошибка: сеть, 408/425/429/5xx; при наличии `Retry-After` значение выводится в stderr.

## 8. Production systemd

Примеры unit/timer находятся в `deploy/systemd/`. Они используют одного непривилегированного пользователя `ceh-unf`, общий `flock` и системный journal. Параллельный импорт и экспорт одной базы не запускаются.

Установите bridge, например, в отдельное virtualenv `/opt/ceh-sklad-unf`, создайте системного пользователя и внешние конфиги:

```bash
sudo useradd --system --home /var/lib/ceh-unf --shell /usr/sbin/nologin ceh-unf
sudo install -d -m 0750 -o root -g ceh-unf /etc/ceh-sklad
sudo install -m 0640 -o root -g ceh-unf unf-tenant.json /etc/ceh-sklad/unf-tenant.json
sudo install -m 0640 -o root -g ceh-unf unf-bridge.env /etc/ceh-sklad/unf-bridge.env
```

`/etc/ceh-sklad/unf-bridge.env` содержит только секреты/URL и не коммитится:

```text
CEH_API_URL=https://sklad.example.ru
CEH_1C_KEY=...
UNF_FRESH_LOGIN=...
UNF_FRESH_PASSWORD=...
```

Скопируйте unit-файлы и включите timers:

```bash
sudo cp deploy/systemd/ceh-unf-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now \
  ceh-unf-health.timer \
  ceh-unf-import-products.timer \
  ceh-unf-import-locations.timer \
  ceh-unf-sync.timer
```

Перед включением `--execute` в production unit обязательно выполните tenant-specific dry-run/UAT. Репозиторные unit-файлы уже содержат `--execute`, поэтому их нельзя активировать до завершения UAT и проверки mapping на целевой базе.

Состояние и журнал:

```bash
systemctl list-timers 'ceh-unf-*'
systemctl status ceh-unf-health.service ceh-unf-sync.service
journalctl -u 'ceh-unf-*' --since today
```

Код `75` оставляет запуск неуспешным и хорошо виден мониторингу; следующий timer выполняет повтор. Код `2` требует исправления прав/конфигурации, код `3` — разбора blocked mapping/outbox/reference objects. Секреты не должны попадать ни в unit-файлы, ни в journal.
