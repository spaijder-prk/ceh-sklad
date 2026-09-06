# Go-live: переход к реальной эксплуатации

Этот документ задаёт порядок допуска production после технического hardening. Секреты, пароли, private keys и пользовательские данные в Git/issue/чат не записываются.

Связанные документы: `docs/GITHUB_RULESET.md`, `docs/PRODUCTION.md`, `docs/BACKUP.md`, `docs/ANDROID_RELEASE.md`, `docs/RELEASE_CHECKLIST.md`.

## Gate 0. Защита исходного кода

Перед первым production deployment:

1. В GitHub активен ruleset `Защита main`.
2. Изменения в `main` идут через pull request.
3. Обязательны `Итоговая проверка проекта` и `Проверить production и Android release-контракты`.
4. Force-push и удаление `main` запрещены.

Gate пройден, когда ruleset Active и оба checks зелёные на release commit.

## Этап 1. Сервер за NAT

Production не требует DNS и не использует входящие стандартные TCP 80/443.

Рекомендуемая схема:

```text
PUBLIC_IP:40022/TCP -> SERVER_LAN_IP:22      # SSH
PUBLIC_IP:40443/TCP -> SERVER_LAN_IP:40443  # HTTPS web/API/WSS
```

Порты могут быть другими. Важно, чтобы:

- SSH и приложение имели отдельные согласованные TCP port-forward;
- сервер имел исходящий интернет;
- `5432`, `8000`, `5173` не публиковались;
- системное время/NTP было корректным.

TLS работает через внутренний Caddy CA (`tls internal`). Публичные 80/443 и Let's Encrypt/ACME не участвуют.

### Production env

```bash
python3 scripts/prepare_production_env.py \
  --ip <REAL_PUBLIC_IP> \
  --port <REAL_HTTPS_PORT>
```

Скрипт создаёт согласованные `CEH_PUBLIC_*` и `CEH_TLS_MODE=internal-ca`.

### Read-only preflight

```bash
python3 scripts/deploy_production.py --check-only
```

Ошибки env/permissions/public-IP/port/origin/Docker/Compose должны быть устранены до запуска.

### Deployment

```bash
python3 scripts/deploy_production.py
```

Deploy получает root CA из Caddy и проверяет `/health` и `/health/ready` через обычную TLS-валидацию internal CA.

**Нельзя** использовать `curl -k`, `verify=false` или обход предупреждения браузера.

## Этап 2. Root CA и первый вход

После deployment:

```bash
python3 scripts/export_internal_ca.py
```

Сохраните SHA-256 fingerprint. Установите `ceh-sklad-root-ca.crt` только на доверенные рабочие компьютеры и Android-устройства.

На рабочем компьютере после установки CA должны без TLS warning открываться:

```text
https://<PUBLIC_IP>:<PORT>
https://<PUBLIC_IP>:<PORT>/health
https://<PUBLIC_IP>:<PORT>/health/ready
```

После этого:

1. войдите bootstrap-администратором;
2. немедленно смените пароль;
3. выйдите и войдите новым паролем;
4. удалите `BOOTSTRAP_ADMIN_LOGIN` и `BOOTSTRAP_ADMIN_PASSWORD` из `.env.production`;
5. выполните:

```bash
python3 scripts/deploy_production.py --skip-backup --no-build
```

Gate пройден, когда root CA fingerprint сверён, TLS warning отсутствует, readiness зелёный и bootstrap credentials удалены.

## Этап 3. Backup, CA disaster recovery и monitoring

До реальных данных:

```bash
./scripts/backup.sh --production
sh scripts/backup_caddy_pki.sh
```

PostgreSQL dump и Caddy PKI backup нужно перенести в защищённое off-site хранилище. Caddy PKI archive содержит private CA key и является секретом.

Для monitor:

```bash
sudo mkdir -p /etc/ceh-sklad
sudo cp ~/.ceh-sklad/tls/ceh-sklad-root-ca.crt /etc/ceh-sklad/ceh-sklad-root-ca.crt
sudo chmod 644 /etc/ceh-sklad/ceh-sklad-root-ca.crt
```

Затем включить/проверить backup и monitor timers и выполнить PostgreSQL restore drill в отдельном контуре.

Gate пройден, когда DB backup/off-site/restore drill успешны, Caddy PKI сохранён off-site, monitoring работает через `CEH_MONITOR_CA_CERT`.

## Этап 4. GitHub CA secret и Android release

Добавьте в GitHub Actions:

```text
CEH_INTERNAL_CA_CERT_BASE64
CEH_ANDROID_KEYSTORE_BASE64
CEH_ANDROID_KEYSTORE_PASSWORD
CEH_ANDROID_KEY_ALIAS
CEH_ANDROID_KEY_PASSWORD
```

`CEH_INTERNAL_CA_CERT_BASE64` — base64 **публичного** root certificate. Caddy CA private key в GitHub не загружается.

Запустите `Подписанный Android release` с:

```text
api_base_url=https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/
```

Workflow до декодирования keystore проверяет backend через internal root CA, точную версию и Alembic head. GitHub Release должен содержать:

```text
ceh-sklad-0.4.0.apk
ceh-sklad-0.4.0.aab
android-release-manifest.json
ceh-sklad-root-ca.crt
SHA256SUMS.txt
```

Root CA включён в checksum.

## Этап 5. Physical-device UAT

На Android сначала установите `ceh-sklad-root-ca.crt` как доверенный пользовательский CA, сверив fingerprint. Release APK не разрешает HTTP и доверяет system/user CA через release network-security config.

Проверить на физическом устройстве:

1. вход по Wi-Fi и мобильной сети;
2. остатки и обе цены;
3. выдача товара представителю;
4. retail sale;
5. wholesale sale;
6. сдача денег и долг;
7. возврат;
8. offline queue;
9. последующая синхронизация без дубля;
10. realtime `wss://IP:PORT` без JWT в URL;
11. смена пароля и инвалидирование старой сессии;
12. журналы/отчёты.

Gate пройден, когда нет потери/дублирования хозяйственных операций.

## Этап 6. Реальная 1С:УНФ

Подключение реального tenant выполняется только после server и Android UAT. Следовать `docs/INTEGRATION_UNF_CLOUD.md` и issue #8.

Сначала tenant audit/metadata/schema lock и небольшой контролируемый набор данных, затем одна операция обмена и проверка идемпотентности. Регулярный production sync включать только после сверки.

## Go / No-Go

Production разрешён только если одновременно:

- ruleset `main` Active;
- оба обязательных CI checks зелёные;
- NAT направляет согласованный SSH и HTTPS port-forward;
- `https://IP:PORT/health` и `/health/ready` зелёные через доверенный internal CA;
- root CA fingerprint сверён на клиентах;
- постоянный пароль администратора проверен, `BOOTSTRAP_ADMIN_*` удалены;
- `5432` и `8000` закрыты извне;
- PostgreSQL backup + off-site + restore drill проверены;
- Caddy PKI private backup сохранён off-site;
- monitoring активен и доверяет internal CA;
- GitHub Release 0.4.0 содержит APK/AAB/manifest/root CA/SHA256SUMS;
- physical-device UAT пройден;
- реальная УНФ прошла контролируемую сверку;
- нет открытого критичного дефекта по остаткам, долгу, деньгам или дублям.

Если хотя бы один пункт не выполнен — **No-Go**.

## Rollback

При критичной проблеме:

1. остановить регулярный обмен с УНФ;
2. зафиксировать affected operation keys/document ids/cursors/время;
3. не удалять idempotency/external ids;
4. сделать дополнительный backup текущего состояния, если БД консистентна;
5. откатить контейнеры на проверенный commit;
6. restore БД выполнять только в окне обслуживания;
7. при потере сервера восстановить старый Caddy PKI **до** открытия клиентов;
8. проверить fingerprint CA, Alembic revision, readiness, остатки/долги/cursors;
9. УНФ sync возобновлять только после повторной сверки.
