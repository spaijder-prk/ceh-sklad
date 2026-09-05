# Чек-лист production-релиза

Этот файл — шаблон приемочного протокола. Результаты конкретного релиза следует сохранять отдельно, не подменяя фактические проверки отметками заранее.

## CI и схема

- [ ] общий CI на release commit полностью зеленый;
- [ ] workflow `Проверка release-контрактов` зеленый для актуального release-контура;
- [ ] SHA release commit зафиксирован: `________________`;
- [ ] номер/ссылка полного CI зафиксированы: `________________`;
- [ ] Alembic revision зафиксирована: `________________`;
- [ ] backup/restore drill успешно пройден;
- [ ] production Compose/Caddy/web image успешно валидированы.

## Инфраструктура

- [ ] рабочий DNS указывает на production-сервер;
- [ ] `https://<домен>/health` успешен;
- [ ] `https://<домен>/health/ready` показывает `status=ready`, `database=ok` и ожидаемую Alembic revision;
- [ ] PostgreSQL `5432` и FastAPI `8000` не опубликованы в интернет;
- [ ] WSS realtime успешно подключается через production TLS;
- [ ] рабочие CORS origins соответствуют фактическому домену;
- [ ] production/staging не используют тестовые `*.invalid`, localhost или debug endpoints.

## Учетные записи и секреты

- [ ] `JWT_SECRET` имеет не менее 32 случайных символов и отличается от тестовых значений;
- [ ] production bootstrap-пароль имеет не менее 12 символов и после первичной настройки заменен при необходимости;
- [ ] ключ интеграции 1С имеет не менее 32 случайных символов и хранится только в secret storage;
- [ ] учетные данные сервисного пользователя УНФ не находятся в Android/web/repository/mapping;
- [ ] учтено, что первый релиз с JWT-отпечатком пароля завершит ранее выданные сессии старого формата;
- [ ] администратор проверил сброс пароля пользователя и последующий вход новым паролем;
- [ ] руководитель/администратор проверил самостоятельную смену пароля в web-панели;
- [ ] торговый представитель проверил самостоятельную смену пароля в Android;
- [ ] после смены/сброса пароля старый Bearer JWT больше не проходит REST, а новое WSS-подключение со старым токеном отклоняется;
- [ ] rate limit входа проверен: 429 показывает корректный `Retry-After`, web/Android не маскируют блокировку под неверный пароль.

## Android

- [ ] production signing key создан один раз и сохранен в защищенной офлайн-копии вместе с backup-параметрами;
- [ ] четыре `CEH_ANDROID_*` release secrets настроены в GitHub Actions;
- [ ] workflow `Подписанный Android release` запущен с текущего HEAD `main` после зеленого общего CI;
- [ ] workflow `Подписанный Android release` успешен;
- [ ] GitHub Release имеет уникальный tag `android-v<versionName>`;
- [ ] Release содержит `ceh-sklad-<version>.apk`, `ceh-sklad-<version>.aab`, `android-release-manifest.json` и `SHA256SUMS.txt`;
- [ ] встроенная перепроверка `scripts/verify_android_release.py` внутри workflow успешна;
- [ ] после скачивания Release отдельно выполнен `scripts/verify_android_release.py`;
- [ ] SHA-256 APK совпадает с `artifact_sha256` в manifest;
- [ ] SHA256SUMS подтверждает APK, AAB и manifest;
- [ ] SHA-256 сертификата из `apksigner --print-certs` совпадает с `signer_certificate_sha256`;
- [ ] подпись AAB успешно проверена `jarsigner`;
- [ ] `application_id=ru.ceh.sklad`, `versionCode` и `versionName` в manifest ожидаемые;
- [ ] `api_base_url` в manifest — фактический production HTTPS origin;
- [ ] `source_commit` в manifest совпадает с release commit;
- [ ] workflow `Android инструментальные smoke-тесты` успешен на эмуляторе;
- [ ] просмотрен artifact `ceh-sklad-android-smoke`: JUnit/HTML, logcat, screenshot и package dump;
- [ ] проверена установка/обновление подписанного APK на целевом устройстве;
- [ ] торговый представитель выполнил login/остатки/продажу/возврат/сдачу денег/offline queue на целевом устройстве;
- [ ] подтверждено, что signing key не будет ротироваться между обычными обновлениями приложения.

## Staging и нагрузка

- [ ] `scripts/release_preflight.py` успешен для staging с ожидаемой Alembic revision;
- [ ] JSON artifact `staging-release-preflight` сохранен в приемочный протокол;
- [ ] workflow `Staging-приемка` успешен в read-only режиме;
- [ ] финальный staging прогон выполнен с `require_unf_ready=true`;
- [ ] WSS, представитель, остатки, задолженность и история операций читаются на staging;
- [ ] согласованная нагрузка выполнена без неожиданного изменения production-данных;
- [ ] если выполнялись реальные тестовые продажи, использован явный `execute_sales=true` и тестовые данные затем сверены;
- [ ] success rate: `________`;
- [ ] throughput: `________ req/s`;
- [ ] p95: `________ ms`;
- [ ] подтверждена идемпотентность повторной доставки mobile/server операций.

## 1С:УНФ Cloud / 1С:Фреш

- [ ] подтверждены провайдер, URL приложения, версия УНФ и часовой пояс базы;
- [ ] сервисный пользователь имеет только согласованные минимальные права;
- [ ] `ceh-unf-fresh-probe --details --all --snapshot ...` выполнен на фактическом tenant;
- [ ] metadata snapshot сохранен как внутренний UAT artifact; его `snapshot_sha256` зафиксирован: `________________`;
- [ ] non-secret tenant mapping заполнен только по реальному `$metadata`/snapshot;
- [ ] `ceh-unf-metadata-validate` возвращает `ready` для exact snapshot+mapping;
- [ ] `mapping_sha256` из offline-validator зафиксирован: `________________`;
- [ ] exact mapping с этим SHA-256 сохранен в release record без credentials;
- [ ] `ceh-unf-tenant-audit` возвращает `ready`;
- [ ] `ceh-unf-fresh-health` возвращает `ready` и подтверждает backend readiness, текущий `$metadata`, поля импорта, reference checks и build payload;
- [ ] выбраны разные реальные виды цен: розничный и оптовый;
- [ ] согласованы организация, центральный склад, allow-list складов представителей, касса, статья ДДС, покупатели и payer mappings;
- [ ] `reference_checks` настроены для кассы, статьи ДДС, реально используемых payer и других обязательных tenant-specific объектов;
- [ ] импорт номенклатуры и двух видов цен выполнен и повтор того же содержимого идемпотентен;
- [ ] импортированы только явно разрешенные склады;
- [ ] выдача/перемещение/возврат создают ожидаемые `Перемещение запасов`;
- [ ] retail и wholesale продажи создают `Расходная накладная` с правильным покупателем и исторической ценой;
- [ ] сдача денег создает `Поступление в кассу` с правильным payer/кассой/статьей ДДС;
- [ ] mixed adjustment создает оприходование + списание и подтверждается batch-confirm;
- [ ] повторная доставка не создает второй документ УНФ;
- [ ] искусственный обрыв после create до confirm восстанавливается find-before-create без дубля;
- [ ] итоговые остатки ceh-sklad и УНФ сверены после UAT;
- [ ] отдельно согласовано правило `DeletionMark`/архивирования товара с ненулевым остатком;
- [ ] systemd health/import/sync timers установлены, writer lock работает, journal проверен;
- [ ] коды `2`, `3` и `75` bridge учтены в эксплуатационной реакции/алертах.

## Приемка и откат

- [ ] администратор проверил справочники, остатки и операции;
- [ ] руководитель проверил отчетность и задолженность;
- [ ] торговый представитель прошел типовой рабочий сценарий на Android;
- [ ] выполнен отдельный restore test из актуального production-compatible backup;
- [ ] определена процедура отката backend/web и восстановления БД;
- [ ] зафиксирована процедура доставки следующего Android-релиза и сохранен signer certificate fingerprint;
- [ ] ссылки на CI, staging preflight, Android release/smoke assets, metadata snapshot/mapping SHA-256 и UAT-протокол собраны в одном release record;
- [ ] issues #7 и #8 закрыты только после фактического production deployment, физического Android UAT и UAT с реальным tenant УНФ.
