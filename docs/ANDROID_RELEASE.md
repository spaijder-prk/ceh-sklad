# Сборка Android для тестирования и production

## Debug

Debug-сборка предназначена для Android Emulator и обращается к backend по `http://10.0.2.2:8000/`. Только debug-манифест разрешает cleartext HTTP.

```bash
./android/gradlew -p android :app:assembleDebug
```

## Production URL

Release-сборка запрещает HTTP. Production URL должен совпадать с фактическим HTTPS origin по публичному IP и нестандартному порту:

```text
https://<PUBLIC_IP>:<PORT>/
```

Например:

```text
https://<PUBLIC_IP>:40443/
```

Если Gradle property не задано, APK получает заведомо нерабочий `https://not-configured.invalid/`.

## Внутренний CA

Production не использует Let's Encrypt и не требует внешних TCP 80/443. Caddy использует `tls internal` и хранит свой CA в persistent `caddy_data`.

После первого запуска сервера экспортируйте публичный root certificate:

```bash
python3 scripts/export_internal_ca.py
```

Файл по умолчанию:

```text
~/.ceh-sklad/tls/ceh-sklad-root-ca.crt
```

Перед первым запуском release APK этот root CA необходимо установить на Android-устройство как пользовательский доверенный CA. Release network-security config разрешает доверие к system CA и user CA, но `cleartextTrafficPermitted=false` остаётся обязательным.

Не отключайте TLS verification и не используйте HTTP.

## Production signing key

Keystore и пароли нельзя хранить в Git. Production signing key создаётся один раз и используется для всех обновлений приложения.

```bash
python scripts/prepare_android_signing.py \
  --repository spaijder-prk/ceh-sklad \
  --upload-secrets
```

Helper создаёт постоянный key вне репозитория и загружает четыре signing secrets:

```text
CEH_ANDROID_KEYSTORE_BASE64
CEH_ANDROID_KEYSTORE_PASSWORD
CEH_ANDROID_KEY_ALIAS
CEH_ANDROID_KEY_PASSWORD
```

Обязательно сохраните keystore и backup JSON в двух защищённых местах.

## Root CA для GitHub Actions

Дополнительно нужно создать GitHub Secret:

```text
CEH_INTERNAL_CA_CERT_BASE64
```

Это **base64 публичного** `ceh-sklad-root-ca.crt`. Приватный CA key Caddy сюда никогда не загружается.

Linux-команда для подготовки значения без переносов строк:

```bash
base64 -w 0 ~/.ceh-sklad/tls/ceh-sklad-root-ca.crt
```

Полученное значение добавляется в GitHub → Repository → Settings → Secrets and variables → Actions → New repository secret.

## Workflow `Подписанный Android release`

Запускайте workflow только после рабочего production backend.

Input `api_base_url`:

```text
https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/
```

Workflow:

1. разрешает release только с актуального HEAD `main`;
2. требует зелёные `Проверка проекта` и `Проверка release-контрактов` на том же commit;
3. проверяет локальные release-contract unit tests;
4. требует `CEH_INTERNAL_CA_CERT_BASE64` и четыре Android signing secrets;
5. декодирует только публичный root CA;
6. до доступа к keystore проверяет `/health/ready` через этот CA;
7. требует точную версию из `VERSION` и единственный актуальный Alembic head;
8. только после успешной проверки backend декодирует production keystore;
9. собирает подписанные APK и AAB;
10. проверяет APK через `apksigner`, AAB через `jarsigner`;
11. формирует `android-release-manifest.json`;
12. включает `ceh-sklad-root-ca.crt` в release;
13. формирует `SHA256SUMS.txt` для APK, AAB, manifest и root CA;
14. независимо перепроверяет все четыре файла;
15. запрещает повторную публикацию существующего `android-v<versionName>`;
16. публикует GitHub Release;
17. удаляет временные keystore/root CA с runner.

## Независимая проверка скачанного release

После скачивания release выполните:

```bash
APKSIGNER=$(find "$ANDROID_HOME/build-tools" -type f -name apksigner | sort -V | tail -1)

python scripts/verify_android_release.py \
  --apk ceh-sklad-0.4.0.apk \
  --aab ceh-sklad-0.4.0.aab \
  --manifest android-release-manifest.json \
  --ca-cert ceh-sklad-root-ca.crt \
  --checksums SHA256SUMS.txt \
  --apksigner "$APKSIGNER" \
  --expected-api-base-url https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/ \
  --expected-source-commit <40-символьный-SHA>
```

Verifier проверяет:

- SHA-256 APK/AAB/manifest/root CA;
- APK signer certificate;
- AAB signature;
- package/version;
- production API URL;
- source commit.

## Установка root CA на Android

Точное название пунктов зависит от производителя Android, но общий путь обычно находится в Settings → Security/Privacy → Encryption & credentials → Install a certificate → CA certificate.

Перед установкой сверяйте SHA-256 fingerprint root CA со значением, полученным непосредственно на production server командой:

```bash
python3 scripts/export_internal_ca.py
```

После установки CA и APK проверьте приложение и по Wi-Fi, и по мобильной сети.

Если устройство сообщает о недоверенном сертификате, не обходите ошибку: сначала проверьте, что установлен правильный root CA.

## Перед production-публикацией

1. Развернуть backend на `https://IP:PORT`.
2. Экспортировать root CA и сверить fingerprint.
3. Установить CA на тестовый рабочий компьютер и Android.
4. Проверить `/health` и `/health/ready` без TLS warnings.
5. Добавить `CEH_INTERNAL_CA_CERT_BASE64` в GitHub Secrets.
6. Создать production Android signing key и сохранить backup.
7. Запустить `Подписанный Android release`.
8. Скачать APK/AAB/manifest/root CA/SHA256SUMS и независимо проверить verifier.
9. Установить APK на физическом Android.
10. Пройти login, остатки, retail/wholesale sale, возврат, сдачу денег, realtime и offline queue.
11. Не менять signing key и Caddy CA без процедуры миграции доверия.
