# Production-развертывание по IP и нестандартному порту

## Поддерживаемая схема

`ceh-sklad` может работать без домена и без доступных снаружи TCP 80/443. Для вашей инфраструктуры используется внутренний CA Caddy и один отдельный внешний HTTPS-порт.

Пример:

```text
PUBLIC_IP:40022/TCP -> SERVER_LAN_IP:22      # SSH
PUBLIC_IP:40443/TCP -> SERVER_LAN_IP:40443  # Цех Склад HTTPS
```

Исходящий интернет с production host нужен для Git/Docker/обновлений, но выпуск TLS-сертификата не требует входящих 80/443.

В `docker-compose.production.yml` PostgreSQL и FastAPI остаются только во внутренней Docker-сети. Наружу публикуется только `CEH_PUBLIC_PORT -> caddy:443`. Порты `5432` и `8000` не публикуются.

Caddy закреплён на `2.11.3-alpine` и использует:

```caddy
https://{$CEH_PUBLIC_HOST} {
    tls internal
}
```

Внутренний CA автоматически создаёт и обновляет leaf-сертификат для IP. Его root CA хранится в постоянном `caddy_data` volume. Клиенты должны явно доверять этому root CA.

## 1. Подготовка сервера и NAT

До запуска:

1. сервер должен иметь постоянный LAN IP;
2. NAT должен иметь стабильный публичный IPv4/IPv6;
3. выберите нестандартный внешний SSH-порт, например `40022`;
4. выберите нестандартный внешний HTTPS-порт, например `40443`;
5. настройте port-forward SSH на серверный `22`;
6. настройте port-forward HTTPS на тот же `CEH_PUBLIC_PORT` сервера;
7. не открывайте `5432`, `8000`, `5173`;
8. установите Docker Engine и Docker Compose plugin;
9. проверьте системное время/NTP;
10. убедитесь, что сервер имеет исходящий доступ в интернет.

Внешние TCP `80` и `443` для `ceh-sklad` не нужны.

## 2. Создание `.env.production`

```bash
python3 scripts/prepare_production_env.py \
  --ip <REAL_PUBLIC_IP> \
  --port <REAL_HTTPS_PORT>
```

Пример формы команды:

```bash
python3 scripts/prepare_production_env.py --ip <PUBLIC_IP> --port 40443
```

Генератор создаёт:

```text
CEH_PUBLIC_IP=<public IP NAT>
CEH_PUBLIC_HOST=<IP или [IPv6]>
CEH_PUBLIC_PORT=<port>
CEH_PUBLIC_ORIGIN=https://<IP>:<port>
CEH_PUBLIC_WS_ORIGIN=wss://<IP>:<port>
CEH_TLS_MODE=internal-ca
```

и безопасно генерирует PostgreSQL/JWT/bootstrap/1С credentials. Файл создаётся с mode `0600`, никогда не перезаписывается и не печатает секреты.

## 3. Read-only preflight

```bash
python3 scripts/deploy_production.py --check-only
```

Проверяется:

- `.env.production` и его права;
- публичность IP;
- диапазон порта;
- точное соответствие IP/port/origin/WSS-origin;
- `CEH_TLS_MODE=internal-ca`;
- Docker daemon/Compose;
- итоговая production Compose-конфигурация.

## 4. Первый запуск

```bash
python3 scripts/deploy_production.py
```

Backend при старте применяет `alembic upgrade head`. Caddy создаёт внутренний PKI и leaf-сертификат для IP. Deployment получает root CA напрямую из Caddy container и проверяет внешний `/health` и `/health/ready` через обычную TLS-валидацию этого root CA. `ssl verification` не отключается.

При обычном последующем обновлении работающей БД deploy предварительно делает production backup, если явно не задан `--skip-backup`.

## 5. Экспорт root CA

После первого запуска:

```bash
python3 scripts/export_internal_ca.py
```

По умолчанию public root certificate будет сохранён в:

```text
~/.ceh-sklad/tls/ceh-sklad-root-ca.crt
```

Скрипт выводит SHA-256 fingerprint. Приватный ключ CA не экспортируется.

Этот root certificate не является секретом. Его можно передавать пользователям системы, но fingerprint нужно сверять через доверенный канал.

## 6. Доверие на рабочих компьютерах

Для web-панели установите `ceh-sklad-root-ca.crt` в Trusted Root Certification Authorities ОС/браузера только на доверенных рабочих компьютерах. После установки перезапустите браузер.

Рабочий адрес:

```text
https://PUBLIC_IP:40443
```

или другой фактически выбранный порт.

Нельзя использовать `curl -k`, `verify=false`, «продолжить несмотря на ошибку сертификата» и другие способы отключения TLS verification.

## 7. Доверие на Android

Release Android по-прежнему имеет `android:usesCleartextTraffic=false`. Для release source-set задан network security config, который доверяет системным CA и CA, установленным пользователем.

До первого запуска приложения установите тот же `ceh-sklad-root-ca.crt` как пользовательский CA на контролируемое Android-устройство и сверяйте fingerprint.

GitHub Release содержит root CA рядом с APK/AAB и включает его в `SHA256SUMS.txt`.

## 8. GitHub Secret root CA

После экспорта root CA загрузите **публичный сертификат** в GitHub Secret:

```text
CEH_INTERNAL_CA_CERT_BASE64
```

Значение — base64 содержимого `ceh-sklad-root-ca.crt`. Это не CA private key. Приватные Caddy PKI ключи в GitHub не загружаются.

Этот secret используют:

- `Подписанный Android release` для проверки production backend;
- `Staging-приемка` для HTTPS/WSS/load-test через private CA.

## 9. Bootstrap admin

Перед первым входом сохраните `BOOTSTRAP_ADMIN_PASSWORD` из `.env.production` в менеджере паролей.

После первого входа:

1. смените пароль;
2. выйдите;
3. подтвердите повторный вход новым паролем;
4. удалите обе строки `BOOTSTRAP_ADMIN_LOGIN` и `BOOTSTRAP_ADMIN_PASSWORD`;
5. выполните:

```bash
python3 scripts/deploy_production.py --skip-backup --no-build
```

Bootstrap credentials являются временным секретом первого запуска. Существующий администратор хранится в PostgreSQL; удаление bootstrap-пары не удаляет пользователя.

## 10. Production monitoring

Скопируйте публичный root CA:

```bash
sudo mkdir -p /etc/ceh-sklad
sudo cp ~/.ceh-sklad/tls/ceh-sklad-root-ca.crt /etc/ceh-sklad/ceh-sklad-root-ca.crt
sudo chmod 644 /etc/ceh-sklad/ceh-sklad-root-ca.crt
```

`deploy/systemd/ceh-monitor.service` задаёт:

```text
CEH_MONITOR_CA_CERT=/etc/ceh-sklad/ceh-sklad-root-ca.crt
```

и monitor выполняет TLS verification через этот CA.

## 11. Backup и disaster recovery PKI

PostgreSQL backup выполняется обычными скриптами `backup.sh --production` и `backup_offsite.sh`.

Кроме БД необходимо сохранить возможность восстановить Caddy internal PKI. Потеря `caddy_data` означает создание нового CA, после чего старые клиентские trust stores перестанут доверять серверу. Поэтому snapshot/backup production host должен включать persistent Caddy data/PKI либо отдельную защищённую копию этого volume.

Root certificate можно распространять публично, **private key Caddy CA должен оставаться секретным**.

## 12. Проверка внешней сети

С другой сети проверьте:

```text
PUBLIC_IP:40022  доступен только для SSH
PUBLIC_IP:40443  доступен для приложения
PUBLIC_IP:5432   закрыт
PUBLIC_IP:8000   закрыт
```

Стандартные `80/443`, принадлежащие другой инфраструктуре, не участвуют в работе `ceh-sklad`.

## 13. Android production release

После server UAT:

1. экспортируйте root CA;
2. добавьте `CEH_INTERNAL_CA_CERT_BASE64` в GitHub Secrets;
3. создайте/загрузите Android signing secrets;
4. запустите `Подписанный Android release` с:

```text
https://PUBLIC_IP:40443/
```

Workflow сначала проверяет backend version/schema/TLS через указанный root CA, только затем декодирует keystore и собирает подписанные APK/AAB.

## 14. Итоговый production checklist

1. `/health` = `ok` через `https://IP:PORT`.
2. `/health/ready` = `ready`, PostgreSQL `ok`, версия и Alembic revision верны.
3. Browser/Android доверяют именно ожидаемому root CA.
4. Root CA fingerprint сверён.
5. Внешние `5432` и `8000` закрыты.
6. Bootstrap credentials удалены после смены пароля.
7. Backup + off-site + restore drill выполнены.
8. Caddy PKI включён в disaster-recovery план.
9. Monitor работает с `CEH_MONITOR_CA_CERT`.
10. Подписанный Android release и physical-device UAT завершены.

Полная последовательность допуска описана в `docs/GO_LIVE.md`.
