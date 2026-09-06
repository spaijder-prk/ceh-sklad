# Чек-лист production-релиза

Этот файл — шаблон фактического приемочного протокола. Не отмечайте пункты заранее.

## CI и исходный код

- [ ] release commit зафиксирован: `________________`;
- [ ] `Итоговая проверка проекта` зелёная;
- [ ] `Проверка release-контрактов` зелёная;
- [ ] активен ruleset `Защита main`;
- [ ] Alembic revision зафиксирована: `________________`;
- [ ] production Compose/Caddy/web/Android release-конфигурация прошли CI.

## NAT, IP и нестандартные порты

- [ ] публичный IP NAT: `________________`;
- [ ] внешний SSH-порт: `________________`;
- [ ] внешний HTTPS-порт приложения: `________________`;
- [ ] NAT SSH направлен только на серверный SSH;
- [ ] NAT HTTPS направлен на тот же `CEH_PUBLIC_PORT` production host;
- [ ] стандартные TCP `80/443` не требуются `ceh-sklad` и не перенастраивались;
- [ ] `CEH_PUBLIC_ORIGIN=https://IP:PORT` точно соответствует фактическому endpoint;
- [ ] `CEH_TLS_MODE=internal-ca`;
- [ ] `5432`, `8000`, `5173` не доступны извне;
- [ ] WSS работает через `wss://IP:PORT/api/v1/realtime` без JWT в URL;
- [ ] production нигде не использует HTTP, localhost или `*.invalid`.

## Internal CA

- [ ] `python3 scripts/export_internal_ca.py` выполнен;
- [ ] сохранён SHA-256 fingerprint root CA: `________________`;
- [ ] root CA установлен на доверенном рабочем компьютере;
- [ ] браузер открывает `https://IP:PORT` без предупреждения TLS;
- [ ] `/health` и `/health/ready` проходят без `-k`/insecure bypass;
- [ ] root CA установлен на тестовом Android-устройстве;
- [ ] в GitHub Actions задан `CEH_INTERNAL_CA_CERT_BASE64` с **публичным** root certificate;
- [ ] Caddy CA private key не загружен в GitHub и не публикуется;
- [ ] выполнен `sh scripts/backup_caddy_pki.sh`;
- [ ] закрытый PKI backup с `root.key` отправлен в защищённое off-site хранилище.

## Учетные записи и секреты

- [ ] `JWT_SECRET` случайный и не короче 32 символов;
- [ ] bootstrap admin вошёл и сразу сменил временный пароль;
- [ ] выполнен выход и повторный вход новым паролем;
- [ ] `BOOTSTRAP_ADMIN_LOGIN` и `BOOTSTRAP_ADMIN_PASSWORD` удалены из production env;
- [ ] ключ 1С случайный и хранится только в secret storage;
- [ ] reset/change password инвалидирует старые REST/WSS сессии;
- [ ] login lockout/`Retry-After` проверены.

## Backup и monitoring

- [ ] выполнен `scripts/backup.sh --production`;
- [ ] dump проходит `pg_restore --list`, checksum совпадает;
- [ ] DB backup отправлен off-site;
- [ ] restore drill выполнен в отдельном контуре;
- [ ] Caddy PKI backup проверен и находится off-site;
- [ ] `/etc/ceh-sklad/ceh-sklad-root-ca.crt` установлен для monitor;
- [ ] monitor использует `CEH_MONITOR_CA_CERT`;
- [ ] backup/monitor timers активны;
- [ ] свободное место на диске достаточно.

## Android release

- [ ] постоянный production signing key создан один раз и имеет офлайн-копию;
- [ ] четыре `CEH_ANDROID_*` signing secrets настроены;
- [ ] `CEH_INTERNAL_CA_CERT_BASE64` настроен;
- [ ] workflow `Подписанный Android release` запущен с текущего HEAD `main`;
- [ ] `api_base_url` = точный `https://IP:PORT/`;
- [ ] backend verifier **до декодирования keystore** подтвердил TLS через internal CA, exact version и Alembic head;
- [ ] GitHub Release имеет уникальный tag `android-v<versionName>`;
- [ ] Release содержит `ceh-sklad-<version>.apk`;
- [ ] Release содержит `ceh-sklad-<version>.aab`;
- [ ] Release содержит `android-release-manifest.json`;
- [ ] Release содержит `ceh-sklad-root-ca.crt`;
- [ ] Release содержит `SHA256SUMS.txt`;
- [ ] SHA256SUMS подтверждает APK, AAB, manifest и root CA;
- [ ] отдельный `scripts/verify_android_release.py --ca-cert ceh-sklad-root-ca.crt ...` успешен;
- [ ] signer certificate fingerprint зафиксирован;
- [ ] `application_id=ru.ceh.sklad`, versionCode/versionName ожидаемые;
- [ ] source commit и API base URL в manifest совпадают с production;
- [ ] APK установлен только после установки и сверки root CA.

## Physical Android UAT

- [ ] login по Wi-Fi;
- [ ] login по мобильной сети;
- [ ] остатки;
- [ ] retail sale;
- [ ] wholesale sale;
- [ ] возврат;
- [ ] сдача денег;
- [ ] долг;
- [ ] offline queue;
- [ ] последующая синхронизация без дубля;
- [ ] realtime WSS;
- [ ] смена пароля инвалидирует старую сессию;
- [ ] журналы backend/web совпадают с ожидаемыми операциями.

## Staging / controlled acceptance

- [ ] `CEH_INTERNAL_CA_CERT_BASE64` доступен staging workflow;
- [ ] `scripts/verify_release_backend.py` успешен с internal CA;
- [ ] `scripts/release_preflight.py` успешен;
- [ ] `Staging-приемка` успешна в read-only режиме;
- [ ] WSS/representative/read endpoints проверены;
- [ ] load-test dry-run сохранён;
- [ ] если `execute_sales=true`, тестовые продажи явно учтены как реальные тестовые документы;
- [ ] success rate: `________`;
- [ ] throughput: `________ req/s`;
- [ ] p95: `________ ms`.

## 1С:УНФ Cloud / 1С:Фреш

- [ ] подтверждены tenant URL, версия УНФ и часовой пояс;
- [ ] сервисный пользователь имеет минимальные права;
- [ ] реальный `$metadata`/snapshot получен;
- [ ] schema lock/mapping подтверждены;
- [ ] `ceh-unf-tenant-audit` = ready;
- [ ] `ceh-unf-fresh-health` = ready;
- [ ] выбраны реальные виды цен и reference mappings;
- [ ] импорт товаров/цен/складов повторяем без дублей;
- [ ] выдача/возврат/retail/wholesale/cash создают ожидаемые документы;
- [ ] retry после неопределённого ответа не создаёт дубль;
- [ ] итоговые остатки сверены.

## Итоговый Go/No-Go

- [ ] production HTTPS по `IP:PORT` работает через доверенный internal CA;
- [ ] DB и Caddy PKI backup/off-site/restore strategy проверены;
- [ ] Android 0.4.0 проверен на физическом устройстве;
- [ ] реальная УНФ прошла controlled UAT;
- [ ] нет критичного дефекта по остаткам, долгу, деньгам или дублям;
- [ ] issue #7 закрывается только после production + Android UAT;
- [ ] issue #8 закрывается только после фактического tenant UAT.
