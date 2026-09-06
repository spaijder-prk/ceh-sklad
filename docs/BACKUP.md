# Резервное копирование и восстановление

## Что резервируется

Основным источником хозяйственных данных является PostgreSQL: справочники, остатки, документы движений, денежный регистр, аудит и журнал обмена с 1С.

При production с `CEH_TLS_MODE=internal-ca` вторым критичным состоянием является **Caddy PKI**. Он содержит private key внутреннего CA. Если потерять этот ключ, новый Caddy CA будет другим и ранее настроенные компьютеры/Android перестанут доверять серверу.

## 1. Production backup PostgreSQL

```bash
./scripts/backup.sh --production
```

Production-вариант использует `.env.production` и `docker-compose.production.yml`. Dump custom-format создаётся в `backups/` с закрытыми правами (`umask 077`), проверяется `pg_restore --list`, рядом формируются SHA-256 и metadata.

Обычный deployment уже работающей установки делает backup БД перед обновлением, если явно не задан `--skip-backup`.

## 2. Backup Caddy internal PKI

После первого успешного запуска и затем после инфраструктурных изменений выполните:

```bash
sh scripts/backup_caddy_pki.sh
```

Будут созданы:

```text
backups/ceh_sklad_caddy_pki_YYYYMMDD_HHMMSS.tar.gz
backups/ceh_sklad_caddy_pki_YYYYMMDD_HHMMSS.tar.gz.sha256
```

Скрипт проверяет, что архив содержит `root.crt` и `root.key`, создаёт SHA-256 и выставляет закрытые права.

**Этот архив является секретом**, потому что содержит private key CA. Не кладите его в GitHub, issue, чат или публичное хранилище.

Публичный root certificate, который экспортирует `scripts/export_internal_ca.py`, секретом не является. Не путайте его с PKI backup.

## 3. Off-site

Каталог `backups/` на production server не должен быть единственной копией.

Для БД можно использовать:

```bash
./scripts/backup_offsite.sh
```

с настроенным `CEH_BACKUP_OFFSITE_DIR` или `CEH_BACKUP_RCLONE_REMOTE`.

Caddy PKI archive также необходимо скопировать в защищённое off-site хранилище. Желательно дополнительное шифрование хранилища/архива и отдельные credentials доступа.

Минимально храните:

- актуальные ежедневные PostgreSQL dumps;
- несколько предыдущих PostgreSQL dumps;
- последнюю проверенную копию Caddy PKI;
- Android production signing keystore и его recovery JSON отдельно от сервера.

## 4. Проверка PostgreSQL backup

Наличие файла недостаточно. Периодически выполняйте тестовое восстановление на отдельной БД/сервере и проверяйте:

- вход администратора;
- количество складов и товаров;
- остатки;
- задолженности представителей;
- последние товарные и денежные операции;
- журнал 1С.

## 5. Восстановление PostgreSQL

> Команда очищает текущие таблицы и заменяет данные содержимым резервной копии. Не запускайте её «для проверки» поверх production.

Development:

```bash
./scripts/restore.sh backups/ceh_sklad_YYYYMMDD_HHMMSS.dump
```

Production:

```bash
./scripts/restore.sh --production backups/ceh_sklad_YYYYMMDD_HHMMSS.dump
```

Скрипт останавливает backend, выполняет `pg_restore --clean --if-exists`, затем запускает backend обратно. После успешного восстановления ждёт `/health/ready`; backend применяет `alembic upgrade head`.

## 6. Восстановление Caddy PKI

Это аварийная операция. В нормальной эксплуатации просто сохраняйте persistent `caddy_data` volume.

Если production server потерян, сначала восстановите Docker/Compose и **старый Caddy PKI до выдачи нового CA**. Архив содержит путь `caddy/pki/...`, соответствующий `/data/caddy/pki` внутри Caddy container.

После восстановления обязательно:

1. проверить SHA-256 архива;
2. проверить fingerprint экспортированного `root.crt`;
3. убедиться, что fingerprint совпадает с CA, который установлен на клиентских устройствах и записан в release evidence;
4. только затем открывать production пользователям.

Если старый CA private key потерян окончательно, потребуется процедура смены доверия: новый root CA, установка его на все компьютеры/Android и новый controlled release/UAT.

## 7. Рекомендуемая политика

1. PostgreSQL backup не реже одного раза в сутки и перед обновлением.
2. Off-site backup с проверкой checksum.
3. Ротация, например 7 ежедневных + 4 недельных + 6 месячных.
4. Caddy PKI backup после первоначального выпуска CA и при изменении PKI.
5. Android signing key минимум в двух защищённых местах вне Git.
6. Регулярный restore drill БД на отдельном окружении.
7. Периодическая сверка Caddy root CA fingerprint.
8. Мониторинг успешности backup jobs.
