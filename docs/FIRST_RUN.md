# Первый запуск Цех Склад

Этот документ разделяет локальный development-запуск и первый production-запуск за NAT. Не используйте development Compose как замену production-контуру.

## 1. Локальный первый запуск

Требования: Docker Engine, Docker Compose v2, Git; `make` необязателен.

```bash
cp .env.example .env
make first-run
```

Без `make`:

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Локально доступны web `http://localhost:5173`, API `http://localhost:8000`, OpenAPI `http://localhost:8000/docs`. PostgreSQL наружу не публикуется.

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/health/ready
```

Для стандартного `.env.example` локальный тестовый логин — `admin`. Эти credentials нельзя переносить в production.

## 2. Production без домена и без внешних 80/443

Gate 0 из `docs/GO_LIVE.md` должен быть пройден: `main` protected, ruleset `Защита main` Active, обязательные CI checks зелёные.

Поддерживаемый production-профиль рассчитан на сервер за NAT:

- есть стабильный публичный IPv4/IPv6 NAT;
- наружу проброшен отдельный нестандартный TCP-порт HTTPS, например `40443`;
- SSH может использовать другой нестандартный порт, например `40022`;
- публичные `80` и `443` проекту не нужны;
- PostgreSQL `5432` и backend `8000` наружу не публикуются;
- исходящий интернет с сервера разрешён для Git/Docker/обновлений;
- TLS выпускается внутренним CA Caddy (`tls internal`), без Let's Encrypt/ACME.

Например NAT может быть настроен так:

```text
PUBLIC_IP:40022/TCP -> SERVER_LAN_IP:22
PUBLIC_IP:40443/TCP -> SERVER_LAN_IP:40443
```

## 3. Создать production env

Из проверенного release commit на production host:

```bash
python3 scripts/prepare_production_env.py \
  --ip <REAL_PUBLIC_IP> \
  --port <REAL_HTTPS_PORT>
```

Например для выбранного порта `40443`:

```bash
python3 scripts/prepare_production_env.py --ip <REAL_PUBLIC_IP> --port 40443
```

Скрипт создаёт согласованные `CEH_PUBLIC_IP`, `CEH_PUBLIC_HOST`, `CEH_PUBLIC_PORT`, `CEH_PUBLIC_ORIGIN`, `CEH_PUBLIC_WS_ORIGIN` и `CEH_TLS_MODE=internal-ca`. `.env.production` создаётся с правами `0600` и не должен попадать в Git, issue, PR, чат или логи.

Перед запуском сохраните `BOOTSTRAP_ADMIN_PASSWORD` в менеджер паролей.

## 4. Read-only preflight

```bash
python3 scripts/deploy_production.py --check-only
```

Preflight проверяет production env, права файла, публичность IP, точное соответствие IP/port/origin, профиль internal CA, Docker daemon/Compose и итоговую Compose-конфигурацию. Он не меняет контейнеры и данные.

## 5. Первый deployment

```bash
python3 scripts/deploy_production.py
```

На первом запуске рабочей БД ещё нет, поэтому предварительный backup не требуется. Deploy поднимает Caddy, получает его внутренний root CA из постоянного `caddy_data` volume и проверяет `/health`/`/health/ready` через нормальную TLS-валидацию этого CA — без `-k` и без отключения проверки сертификата.

## 6. Экспортировать публичный root CA

После успешного запуска:

```bash
python3 scripts/export_internal_ca.py
```

По умолчанию будет создан:

```text
~/.ceh-sklad/tls/ceh-sklad-root-ca.crt
```

Скрипт также покажет SHA-256 fingerprint. Это **публичный сертификат**, его можно переносить на доверенные клиентские устройства. Приватный ключ CA не экспортируется и остаётся в `caddy_data`.

Сделайте отдельную защищённую резервную копию Caddy data/PKI вместе с инфраструктурными backup: потеря CA private key потребует заново устанавливать доверие на клиентах и перевыпускать Android-контур.

## 7. Установить root CA на рабочий компьютер

До открытия web-панели установите `ceh-sklad-root-ca.crt` в доверенные корневые центры сертификации ОС/браузера. После установки полностью перезапустите браузер.

Проверяйте SHA-256 fingerprint root CA по значению, показанному `export_internal_ca.py`. Не устанавливайте сертификат, полученный из неизвестного источника.

После установки должны открываться без предупреждений:

```text
https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>
https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/health
https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/health/ready
```

Если браузер показывает предупреждение о недоверенном сертификате, не нажимайте «продолжить всё равно»: сначала исправьте установку root CA.

## 8. Первый вход и отключение bootstrap

1. Войти bootstrap-администратором.
2. Немедленно сменить временный пароль.
3. Выйти.
4. Повторно войти новым паролем.
5. Удалить из `.env.production` обе строки `BOOTSTRAP_ADMIN_LOGIN` и `BOOTSTRAP_ADMIN_PASSWORD`.
6. Выполнить:

```bash
python3 scripts/deploy_production.py --skip-backup --no-build
```

После этого `BOOTSTRAP_ADMIN_LOGIN` и `BOOTSTRAP_ADMIN_PASSWORD` должны быть удалены из production env, bootstrap отключён. Существующий администратор остаётся в PostgreSQL.

## 9. Monitoring

Скопируйте root CA для системного monitor:

```bash
sudo mkdir -p /etc/ceh-sklad
sudo cp ~/.ceh-sklad/tls/ceh-sklad-root-ca.crt /etc/ceh-sklad/ceh-sklad-root-ca.crt
sudo chmod 644 /etc/ceh-sklad/ceh-sklad-root-ca.crt
```

`ceh-monitor.service` использует этот файл через `CEH_MONITOR_CA_CERT` и не отключает TLS verification.

## 10. Android

Release Android запрещает cleartext HTTP. На Android-устройстве до первого запуска приложения нужно установить тот же `ceh-sklad-root-ca.crt` как пользовательский CA. Release network-security config доверяет system CA и установленным пользователем CA, но продолжает запрещать HTTP.

GitHub workflow `Подписанный Android release` дополнительно использует `CEH_INTERNAL_CA_CERT_BASE64` для проверки backend и прикладывает тот же `ceh-sklad-root-ca.crt` к GitHub Release вместе с SHA256SUMS.

## 11. Что не включать на первом старте

Не включайте регулярный обмен с реальной облачной 1С:УНФ до завершения physical-device UAT и controlled tenant audit. Первое подключение УНФ выполняется по `docs/INTEGRATION_UNF_CLOUD.md`, `docs/UNF_TENANT_CHECKLIST.md` и issue #8.

Не создавайте production Android signing key внутри репозитория. Используйте `scripts/prepare_android_signing.py`.

## 12. Критерий готовности к реальным данным

Перед реальными хозяйственными данными одновременно должны быть выполнены:

- активна защита `main`;
- release commit имеет зелёные обязательные CI checks;
- NAT пробрасывает только согласованный HTTPS-порт приложения и отдельный SSH-порт;
- внешние `5432` и `8000` закрыты;
- `/health` и `/health/ready` зелёные через `https://IP:PORT`;
- root CA установлен только на доверенные клиентские устройства и fingerprint сверён;
- bootstrap-пароль сменён, повторный вход подтверждён;
- `BOOTSTRAP_ADMIN_LOGIN`/`BOOTSTRAP_ADMIN_PASSWORD` удалены из production env, bootstrap отключён;
- backup + off-site + restore drill проверены;
- Caddy PKI сохранён для disaster recovery;
- monitoring использует internal CA и активен;
- подписанный Android APK содержит точный `https://IP:PORT/`, установленный CA доверен устройством;
- physical-device UAT не выявил потери или дублирования остатков, продаж и денежных операций.

Полный Go/No-Go порядок находится в `docs/GO_LIVE.md`.
