# Go-live: переход к реальной эксплуатации

Этот документ задаёт порядок допуска после технического hardening. Секреты, пароли, приватные ключи и пользовательские данные в отчёты и Git не записываются.

Связанные документы: `docs/GITHUB_RULESET.md`, `docs/PRODUCTION.md`, `docs/BACKUP.md`, `docs/ANDROID_RELEASE.md`, `docs/ANDROID_RELEASE_ARTIFACT.md`, `docs/ANDROID_SMOKE.md`, `docs/INTEGRATION_1C.md`, `docs/INTEGRATION_UNF_CLOUD.md`, `docs/RELEASE_CHECKLIST.md`.

## Gate 0. Защита исходного кода

Перед первым production deployment:

1. В GitHub активен ruleset `Защита main` из `.github/rulesets/main.json`.
2. Изменения в `main` идут через pull request.
3. Обязательные status checks:
   - `Итоговая проверка проекта`;
   - `Проверить production и Android release-контракты`.
4. Force-push и удаление `main` запрещены.
5. Автоматическое обновление lock-файлов создаёт PR, а не пишет напрямую в `main`.

**Gate пройден**, когда ruleset Active и оба обязательных check зелёные на release commit.

## Этап 1. Реальный сервер, публичный IP и порт

Production этого проекта не требует DNS-домена. Один и тот же origin используется web и Android:

```text
https://<PUBLIC_IP>:<HTTPS_PORT>
```

### Сеть

- выделить стабильный публичный IPv4/IPv6;
- выбрать внешний HTTPS-порт приложения;
- TCP `80` направить на Caddy для Let’s Encrypt ACME HTTP-01 и автоматического renewal;
- выбранный TCP HTTPS-порт открыть для web/API/WSS;
- при использовании HTTP/3 открыть тот же UDP-порт;
- PostgreSQL `5432` и backend `8000` не публиковать;
- проверить корректное время/NTP.

Caddy использует Let’s Encrypt IP certificate с ACME profile `shortlived`. Если IP приватный или TCP `80` невозможно предоставить Caddy, этот production-профиль не используется; переход на незашифрованный HTTP запрещён.

### Production env

На сервере, а не в Git:

```bash
python scripts/prepare_production_env.py \
  --ip <REAL_PUBLIC_IP> \
  --port <REAL_HTTPS_PORT> \
  --email <REAL_ACME_EMAIL>
```

Скрипт формирует согласованные:

```text
CEH_PUBLIC_IP
CEH_PUBLIC_HOST
CEH_PUBLIC_PORT
CEH_PUBLIC_ORIGIN
CEH_PUBLIC_WS_ORIGIN
```

Сохранить временный bootstrap password и постоянные секреты в менеджере секретов. Не передавать `.env.production` в issue, PR, чат или логи.

### Read-only preflight

```bash
python scripts/deploy_production.py --check-only
```

Ошибки прав файла, public-IP/port/origin drift, Docker daemon или Compose должны быть устранены до запуска. TCP `80` дополнительно проверяется с внешней сети.

### Deployment

```bash
python scripts/deploy_production.py
```

После старта проверить:

```bash
curl --fail https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/health
curl --fail https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/health/ready
```

Также проверить:

- сертификат публично доверен и содержит фактический IP в SAN;
- web-панель открывается через точный production origin;
- CORS/Origin соответствуют `https://IP:PORT`;
- WSS работает через `wss://IP:PORT/api/v1/realtime` без JWT в URL;
- `5432` и `8000` недоступны извне.

### Закрыть bootstrap после первичной инициализации

1. Войти bootstrap-администратором.
2. Немедленно сменить временный пароль.
3. Выйти и подтвердить повторный вход новым паролем.
4. Удалить из `.env.production` обе строки `BOOTSTRAP_ADMIN_LOGIN` и `BOOTSTRAP_ADMIN_PASSWORD`.
5. Повторно применить Compose:

```bash
python scripts/deploy_production.py --skip-backup --no-build
```

6. Ещё раз проверить `/health/ready` и вход новым паролем.

**Этап 1 пройден**, когда HTTPS/readiness зелёные, сертификат IP валиден, TCP `80` доступен для renewal, наружу открыт только согласованный прикладной HTTPS-порт (и его UDP при необходимости), постоянный пароль администратора проверен, а временные `BOOTSTRAP_ADMIN_*` удалены.

## Этап 2. Production backup и monitoring

До загрузки реальных хозяйственных данных:

1. Выполнить первую production-копию:

```bash
./scripts/backup.sh --production
```

2. Убедиться, что созданы dump, SHA-256 и metadata и dump проходит `pg_restore --list`.
3. Настроить отдельное off-site место — другой сервер/volume/object storage через поддерживаемый `rclone` remote.
4. Выполнить ручную off-site отправку и проверить наличие dump/checksum/metadata на удалённой стороне.
5. Включить ежедневный backup/off-site timer.
6. Включить production-monitor timer с production URL `https://IP:PORT`.
7. Если используется alert webhook — проверить тестовое уведомление.
8. Провести restore drill в отдельную БД/контур.

**Gate пройден**, когда локальная и off-site копии валидны, checksum совпадает, restore drill успешен, monitoring/timers активны.

## Этап 3. Подписанный Android 0.4.0

В GitHub Secrets настроить:

- `CEH_ANDROID_KEYSTORE_BASE64`;
- `CEH_ANDROID_KEYSTORE_PASSWORD`;
- `CEH_ANDROID_KEY_ALIAS`;
- `CEH_ANDROID_KEY_PASSWORD`.

Запустить workflow **`Подписанный Android release`** с параметром:

```text
api_base_url=https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/
```

Workflow должен использовать актуальный protected `main` с зелёными CI, до декодирования keystore проверить production backend по HTTPS, точной версии и Alembic head, затем собрать/проверить APK+AAB и сформировать manifest/SHA256SUMS.

Перед установкой проверить:

- `versionName = 0.4.0`;
- application id `ru.ceh.sklad`;
- API base URL — точный production `https://IP:PORT/`;
- source commit совпадает с release commit;
- SHA-256 APK совпадает с manifest/SHA256SUMS;
- signer certificate SHA-256 соответствует сохранённому production signing certificate.

**Gate пройден**, когда GitHub Release содержит проверенные подписанные APK/AAB и manifest/checksum для одного production commit и одного конкретного IP:port origin.

## Этап 4. Physical-device UAT

UAT выполняется подписанным production APK на физическом Android-устройстве. В отчёт записывать только модель устройства, Android version/API, app version, APK SHA-256, дату, тестовый аккаунт/роль без пароля и результат.

Минимальные сценарии:

1. Первый вход торгового представителя по мобильной сети и Wi-Fi через `https://IP:PORT`.
2. Просмотр остатков нескольких складов и обеих цен.
3. Администратор выдаёт товар представителю; новое состояние появляется на устройстве.
4. Онлайн-продажа уменьшает остаток и увеличивает долг.
5. Сдача денег уменьшает долг и появляется в истории.
6. Возврат корректно меняет оба остатка.
7. Офлайн-продажа сохраняется в очереди без ложного подтверждения.
8. После восстановления сети операция отправляется один раз с тем же operation key.
9. Конфликт/ошибка офлайн-операции виден пользователю и не теряется автоматически.
10. Выход из одного аккаунта и вход другого не показывает/не отправляет чужую очередь.
11. Realtime работает через `wss://IP:PORT` без токена в URL.
12. Смена пароля инвалидирует старую сессию.
13. Переустановка приложения не восстанавливает старую авторизацию из Android Backup.
14. Журнал документов, денежный журнал и отчёт руководителя совпадают с ожидаемыми значениями.

**Gate пройден**, когда критичные сценарии пройдены без потери/дублирования данных.

## Этап 5. Реальная облачная 1С:УНФ

Подключение выполняется только после successful physical-device UAT.

До записи данных определить:

- точный production tenant/URL облачной УНФ;
- версию/вариант УНФ и доступные HTTP/OData/extension interfaces;
- тестовую организацию/склады;
- правила соответствия UUID `ceh-sklad` ↔ GUID/ссылкам УНФ;
- master-систему для товаров, цен, складов, продаж, оплат и возвратов.

Использовать отдельный `INTEGRATION_1C_API_KEY`, не JWT пользователя.

Последовательность:

1. Выполнить tenant audit/probe по `docs/INTEGRATION_UNF_CLOUD.md` без массовой записи.
2. Проверить metadata/сущности/права интеграционной учётной записи.
3. Импортировать/сопоставить небольшой контролируемый набор товаров и складов.
4. Проверить отсутствие дублей external id/GUID.
5. Выполнить одну контролируемую операцию обмена и сверить её по обеим системам.
6. Повтор того же `external_id`/operation key не должен создавать повторную хозяйственную операцию.
7. Проверить incremental cursors и восстановление обмена после остановки.
8. Сверить продажи, возвраты и денежные операции.
9. Сохранить результаты сверки без паролей/ключей.
10. Только после успешной сверки включать регулярный production sync.

## Go / No-Go

Production запуск разрешён только если одновременно выполнено:

- GitHub ruleset `main` Active;
- оба обязательных CI checks зелёные на release commit;
- production HTTPS `https://IP:PORT/health` и `/health/ready` зелёные;
- публично доверенный IP-сертификат валиден и автоматический renewal через TCP `80` возможен;
- постоянный пароль администратора проверен, временные `BOOTSTRAP_ADMIN_*` удалены;
- `5432` и `8000` закрыты извне;
- локальный/off-site backup и restore drill проверены;
- monitoring/timers активны;
- подписанный Android 0.4.0 соответствует production IP:port, commit, checksum и signer certificate;
- physical-device UAT пройден;
- реальная УНФ прошла контролируемую сверку;
- нет открытого критичного дефекта по остаткам, долгу, деньгам или дублям документов.

Если хотя бы один пункт не выполнен — **No-Go**.

## Rollback

При критичной проблеме:

1. остановить регулярный обмен с УНФ;
2. зафиксировать affected operation keys/document ids/integration cursors/время;
3. не удалять и не переиспользовать idempotency/external ids;
4. сделать дополнительный backup текущего состояния, если БД консистентна;
5. откатить контейнеры на проверенный commit по утверждённой процедуре;
6. restore БД выполнять в отдельном окне обслуживания и только при необходимости;
7. после восстановления проверить Alembic revision, `/health/ready`, остатки/долги/cursors;
8. УНФ sync возобновлять только после повторной сверки.

Нельзя исправлять production прямым редактированием таблиц без зафиксированной процедуры и сверки регистров.
