# Чек-лист production-релиза

Этот файл — шаблон приемочного протокола. Результаты конкретного релиза следует сохранять отдельно, не подменяя фактические проверки отметками заранее.

## CI и схема

- [ ] общий CI на release commit полностью зеленый;
- [ ] workflow `Проверка release-контрактов` зеленый;
- [ ] SHA release commit зафиксирован: `________________`;
- [ ] номер/ссылка полного CI зафиксированы: `________________`;
- [ ] Alembic revision зафиксирована: `________________`;
- [ ] backup/restore drill успешно пройден;
- [ ] production Compose/Caddy/web image успешно валидированы.

## Инфраструктура IP + порт

- [ ] зафиксирован реальный публичный IP: `________________`;
- [ ] зафиксирован внешний HTTPS-порт: `________________`;
- [ ] `CEH_PUBLIC_ORIGIN=https://IP:PORT` точно соответствует фактическому endpoint;
- [ ] TCP `80` доступен Caddy извне для Let’s Encrypt ACME HTTP-01 и renewal;
- [ ] сертификат публично доверен и содержит фактический IP в SAN;
- [ ] `https://IP:PORT/health` успешен;
- [ ] `https://IP:PORT/health/ready` показывает `status=ready`, `database=ok`, ожидаемые version и Alembic revision;
- [ ] PostgreSQL `5432` и FastAPI `8000` не опубликованы в интернет;
- [ ] WSS realtime успешно подключается через `wss://IP:PORT/api/v1/realtime` без JWT в URL;
- [ ] CORS origin точно соответствует `https://IP:PORT`;
- [ ] production не использует `*.invalid`, localhost, debug endpoints или HTTP;
- [ ] `scripts/production_monitor.py` проверяет тот же `CEH_PUBLIC_ORIGIN` либо явно заданный HTTPS `CEH_MONITOR_BASE_URL`.

## Учетные записи и секреты

- [ ] `JWT_SECRET` имеет не менее 32 случайных символов и отличается от тестовых значений;
- [ ] bootstrap-администратор вошёл, сменил временный пароль и подтвердил повторный вход новым паролем;
- [ ] `BOOTSTRAP_ADMIN_LOGIN` и `BOOTSTRAP_ADMIN_PASSWORD` удалены из production env после первичной настройки;
- [ ] ключ интеграции 1С имеет не менее 32 случайных символов и хранится только в secret storage;
- [ ] учетные данные сервисного пользователя УНФ не находятся в Android/web/repository/mapping;
- [ ] администратор проверил сброс пароля пользователя и последующий вход новым паролем;
- [ ] руководитель/администратор проверил самостоятельную смену пароля в web-панели;
- [ ] торговый представитель проверил самостоятельную смену пароля в Android;
- [ ] после смены/сброса пароля старый Bearer JWT больше не проходит REST/WSS;
- [ ] rate limit входа проверен: 429 показывает корректный `Retry-After`.

## Backup и monitoring

- [ ] выполнен `scripts/backup.sh --production`;
- [ ] dump проходит `pg_restore --list` и checksum совпадает;
- [ ] копия отправлена off-site и проверена на удалённой стороне;
- [ ] restore drill выполнен в отдельной БД/контуре;
- [ ] backup/off-site timers активны;
- [ ] monitor timer активен и проверяет `https://IP:PORT`;
- [ ] alert webhook, если используется, проверен тестовым отказом/уведомлением;
- [ ] проверено достаточное свободное место на диске.

## Android

- [ ] production signing key создан один раз и сохранен в защищенной офлайн-копии вместе с backup-параметрами;
- [ ] четыре `CEH_ANDROID_*` release secrets настроены в GitHub Actions;
- [ ] workflow `Подписанный Android release` запущен с текущего HEAD `main` после зеленых обязательных CI;
- [ ] `api_base_url` workflow — точный `https://IP:PORT/`;
- [ ] backend verifier до декодирования keystore подтвердил exact version + Alembic head;
- [ ] workflow `Подписанный Android release` успешен;
- [ ] GitHub Release имеет уникальный tag `android-v<versionName>`;
- [ ] Release содержит `ceh-sklad-<version>.apk`, `ceh-sklad-<version>.aab`, `android-release-manifest.json` и `SHA256SUMS.txt`;
- [ ] встроенная перепроверка `scripts/verify_android_release.py` успешна;
- [ ] после скачивания Release отдельно выполнен `scripts/verify_android_release.py`;
- [ ] SHA-256 APK совпадает с manifest/SHA256SUMS;
- [ ] SHA-256 сертификата из `apksigner --print-certs` совпадает с `signer_certificate_sha256`;
- [ ] подпись AAB успешно проверена `jarsigner`;
- [ ] `application_id=ru.ceh.sklad`, versionCode/versionName ожидаемые;
- [ ] `api_base_url` в manifest — фактический `https://IP:PORT/`;
- [ ] `source_commit` в manifest совпадает с release commit;
- [ ] workflow `Android инструментальные smoke-тесты` успешен на эмуляторе;
- [ ] проверена установка/обновление подписанного APK на целевом устройстве;
- [ ] торговый представитель выполнил login/остатки/продажу/возврат/сдачу денег/realtime/offline queue по Wi-Fi и мобильной сети;
- [ ] signing key не будет ротироваться между обычными обновлениями приложения.

## Staging и нагрузка

- [ ] `scripts/verify_release_backend.py` успешен для staging/release-candidate endpoint;
- [ ] `scripts/release_preflight.py` успешен;
- [ ] JSON artifacts backend-contract/preflight сохранены в приемочный протокол;
- [ ] workflow `Staging-приемка` успешен в read-only режиме;
- [ ] финальный staging прогон выполнен с `require_unf_ready=true` после подключения реального tenant;
- [ ] WSS, представитель, остатки, задолженность и история операций читаются;
- [ ] согласованная нагрузка выполнена без неожиданного изменения production-данных;
- [ ] если выполнялись реальные тестовые продажи, использован явный `execute_sales=true`;
- [ ] success rate: `________`;
- [ ] throughput: `________ req/s`;
- [ ] p95: `________ ms`;
- [ ] подтверждена идемпотентность повторной доставки mobile/server операций.

## 1С:УНФ Cloud / 1С:Фреш

- [ ] подтверждены провайдер, URL приложения, версия УНФ и часовой пояс базы;
- [ ] сервисный пользователь имеет только согласованные минимальные права;
- [ ] `ceh-unf-fresh-probe --details --all --snapshot ...` выполнен на фактическом tenant;
- [ ] metadata snapshot сохранен как внутренний UAT artifact; `snapshot_sha256`: `________________`;
- [ ] non-secret tenant mapping заполнен только по реальному `$metadata`/snapshot;
- [ ] `ceh-unf-metadata-validate` возвращает `ready` для exact snapshot+mapping;
- [ ] `mapping_sha256` зафиксирован: `________________`;
- [ ] `ceh-unf-tenant-audit` возвращает `ready`;
- [ ] `ceh-unf-fresh-health` возвращает `ready`;
- [ ] выбраны разные реальные виды цен: розничный и оптовый;
- [ ] согласованы организация, центральный склад, allow-list складов представителей, касса, статья ДДС, покупатели и payer mappings;
- [ ] `reference_checks` настроены для обязательных tenant-specific объектов;
- [ ] импорт номенклатуры/цен и складов повторяем без дублей;
- [ ] выдача/перемещение/возврат создают ожидаемые документы УНФ;
- [ ] retail/wholesale продажи создают ожидаемые документы с правильной исторической ценой;
- [ ] сдача денег создаёт ожидаемый кассовый документ;
- [ ] повторная доставка не создаёт второй документ УНФ;
- [ ] обрыв после create до confirm восстанавливается find-before-create без дубля;
- [ ] итоговые остатки `ceh-sklad` и УНФ сверены после UAT;
- [ ] systemd health/import/sync timers установлены и journal проверен.

## Приемка и откат

- [ ] администратор проверил справочники, остатки и операции;
- [ ] руководитель проверил отчетность и задолженность;
- [ ] торговый представитель прошел типовой рабочий сценарий на Android;
- [ ] выполнен отдельный restore test из актуального production-compatible backup;
- [ ] определена процедура отката backend/web и восстановления БД;
- [ ] сохранен signer certificate fingerprint для следующих Android-релизов;
- [ ] ссылки на CI, backend preflight, Android release/smoke assets, metadata snapshot/mapping SHA-256 и UAT-протокол собраны в одном release record;
- [ ] issues #7 и #8 закрываются только после фактического production deployment, физического Android UAT и UAT с реальным tenant УНФ.
