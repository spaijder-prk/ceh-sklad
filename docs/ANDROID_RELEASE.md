# Сборка Android для тестирования и production

## Debug

Debug-сборка предназначена для Android Emulator и обращается к backend по адресу `http://10.0.2.2:8000/`. Только debug-манифест разрешает незашифрованный HTTP.

```bash
./android/gradlew -p android :app:assembleDebug
```

В обычном CI готовый `app-debug.apk` сохраняется как артефакт `ceh-sklad-debug-apk`. CI также компилирует release-вариант с тестовым HTTPS URL без production-подписи, чтобы release-конфигурация не ломалась незаметно.

## Release URL

Release-сборка запрещает cleartext HTTP. URL backend передается Gradle-свойством `CEH_API_BASE_URL` и в production должен совпадать с фактическим HTTPS origin вида `https://<PUBLIC_IP>:<PORT>/`.

```bash
./android/gradlew -p android :app:assembleRelease \
  -PCEH_API_BASE_URL=https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/
```

Если внешний порт — `443`, `:443` можно не указывать. Для IPv6 используйте URL-форму с квадратными скобками: `https://[IPv6]:PORT/`.

Если свойство не передано, APK получает заведомо нерабочий адрес `https://not-configured.invalid/`, чтобы тестовая конфигурация не могла случайно обратиться к локальному backend.

Production IP должен иметь публично доверенный TLS-сертификат. Текущий production-профиль получает короткоживущий Let’s Encrypt IP certificate через Caddy; Android не должен отключать проверку TLS или доверять самоподписанному сертификату без отдельного утверждённого pinning/CA-профиля.

## Production signing key

Keystore и пароли нельзя хранить в Git. Production signing key создается один раз и затем должен использоваться для всех обновлений уже установленного приложения.

Рекомендуемый способ подготовки — встроенный helper. Нужен JDK 17+; для автоматической загрузки GitHub Secrets также нужен авторизованный GitHub CLI (`gh auth login`):

```bash
python scripts/prepare_android_signing.py \
  --repository spaijder-prk/ceh-sklad \
  --upload-secrets
```

По умолчанию helper:

- создает PKCS12 key `~/.ceh-sklad/android-signing/ceh-sklad-release.p12`;
- создает `ceh-sklad-signing-backup.json` с параметрами восстановления;
- использует RSA 4096 и срок сертификата 10000 дней;
- создает каталог с правами `0700`, а key/backup — `0600`;
- отказывается создавать signing material внутри Git-репозитория;
- никогда не перезаписывает уже существующий production key;
- передает секреты в `gh secret set` через stdin и не выводит пароли/base64 в консоль.

После создания обязательно сохраните **и keystore, и backup JSON** в защищенной офлайн-копии. Потеря production signing key означает невозможность выпустить обновление поверх уже установленного APK с прежней подписью.

Helper загружает следующие GitHub Secrets:

```text
CEH_ANDROID_KEYSTORE_BASE64
CEH_ANDROID_KEYSTORE_PASSWORD
CEH_ANDROID_KEY_ALIAS
CEH_ANDROID_KEY_PASSWORD
```

Если `--upload-secrets` не используется, эти четыре значения можно настроить вручную из локального backup, не копируя сам backup в репозиторий или issue.

Для локальной подписанной сборки Gradle читает соответствующие переменные окружения:

```text
CEH_ANDROID_KEYSTORE_PATH
CEH_ANDROID_KEYSTORE_PASSWORD
CEH_ANDROID_KEY_ALIAS
CEH_ANDROID_KEY_PASSWORD
```

## Workflow `Подписанный Android release`

Ручной workflow предназначен только для production-релиза. В input `api_base_url` передавайте точный production origin:

```text
https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/
```

Workflow выполняет release-gates:

1. запускается только с текущего HEAD ветки `main`;
2. требует завершенные зелёные `Проверка проекта` и `Проверка release-контрактов` на том же commit;
3. повторно выполняет release-contract тесты;
4. проверяет, что `api_base_url` — чистый HTTPS origin без credentials/path/query/fragment;
5. **до декодирования keystore** выполняет `scripts/verify_release_backend.py`: `/health/ready` обязан вернуть `ready/ok`, точную версию из `VERSION` и единственный актуальный Alembic head;
6. сохраняет JSON-отчет проверки backend как CI artifact даже при отказе gate;
7. декодирует keystore только во временный каталог runner;
8. собирает подписанные APK и AAB;
9. проверяет APK через `apksigner` и AAB через `jarsigner`;
10. формирует `android-release-manifest.json` с SHA-256 APK, fingerprint сертификата, package/version, backend URL и source commit;
11. формирует `SHA256SUMS.txt`;
12. независимо перепроверяет пакет через `scripts/verify_android_release.py`;
13. запрещает повторную публикацию существующего `android-v<versionName>`;
14. публикует GitHub Release;
15. удаляет временный keystore через `always()`.

Backend verifier выполняет только HTTPS `GET /health/ready`, не использует production credentials и не изменяет данные. Он fail-closed при redirect, сетевой/HTTP/JSON ошибке, нескольких Alembic heads или несовпадении схемы/версии.

Перед следующим релизом необходимо увеличить `versionCode` и `versionName` в `android/app/build.gradle.kts`.

## Независимая проверка скачанного release

После скачивания APK/AAB/manifest/SHA256SUMS выполните проверку отдельно от workflow:

```bash
APKSIGNER=$(find "$ANDROID_HOME/build-tools" -type f -name apksigner | sort -V | tail -1)

python scripts/verify_android_release.py \
  --apk ceh-sklad-0.4.0.apk \
  --aab ceh-sklad-0.4.0.aab \
  --manifest android-release-manifest.json \
  --checksums SHA256SUMS.txt \
  --apksigner "$APKSIGNER" \
  --expected-api-base-url https://<REAL_PUBLIC_IP>:<REAL_HTTPS_PORT>/ \
  --expected-source-commit <40-символьный-SHA>
```

Verifier проверяет SHA-256, размеры, APK/AAB signatures, signer certificate fingerprint, package/version, production API URL и source commit.

## Перед production-публикацией

1. Развернуть backend на фактическом `https://IP:PORT` и убедиться, что TLS публично доверен.
2. Проверить `/health/ready` и exact release backend contract.
3. Создать production signing key и сохранить офлайн backup.
4. Убедиться, что четыре `CEH_ANDROID_*` GitHub Secrets настроены.
5. Запустить `Подписанный Android release` с точным `https://IP:PORT/`.
6. Скачать файлы GitHub Release и независимо выполнить verifier.
7. Установить APK на физическом устройстве по Wi-Fi и мобильной сети.
8. Пройти login, остатки, retail/wholesale sale, возврат, сдачу денег, realtime и offline queue.
9. Не менять signing key между обычными обновлениями приложения.
