# Сборка Android для тестирования и production

## Debug

Debug-сборка предназначена для Android Emulator и обращается к backend по адресу `http://10.0.2.2:8000/`. Только debug-манифест разрешает незашифрованный HTTP.

```bash
gradle -p android :app:assembleDebug
```

В обычном CI готовый `app-debug.apk` сохраняется как артефакт `ceh-sklad-debug-apk`. CI также компилирует release-вариант с тестовым HTTPS URL без production-подписи, чтобы release-конфигурация не ломалась незаметно.

## Release URL

Release-сборка запрещает cleartext HTTP. URL backend передается Gradle-свойством `CEH_API_BASE_URL` и для рабочего окружения должен быть HTTPS origin с доступным сертификатом.

```bash
gradle -p android :app:assembleRelease \
  -PCEH_API_BASE_URL=https://sklad.example.ru/
```

Если свойство не передано, APK получает заведомо нерабочий адрес `https://not-configured.invalid/`, чтобы тестовая конфигурация не могла случайно обратиться к локальному backend.

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

Ручной workflow предназначен только для production-релиза и выполняет дополнительные release-gates:

1. запускается только с текущего HEAD ветки `main`;
2. требует уже завершенный зеленый workflow `Проверка проекта` на том же commit;
3. использует Python 3.12 и повторно выполняет release-contract тесты;
4. проверяет, что `api_base_url` — HTTPS origin без credentials/path/query;
5. декодирует keystore только во временный каталог runner;
6. собирает подписанные APK и AAB;
7. проверяет APK через `apksigner` и AAB через `jarsigner`;
8. формирует `android-release-manifest.json` с SHA-256 APK, fingerprint сертификата, package/version, backend URL и source commit;
9. формирует `SHA256SUMS.txt` для APK, AAB и manifest;
10. независимо перепроверяет подготовленный пакет через `scripts/verify_android_release.py`;
11. запрещает повторную публикацию существующего `android-v<versionName>`;
12. публикует постоянный GitHub Release с именованными APK/AAB, manifest и контрольными суммами;
13. удаляет временный keystore через `always()`.

Перед следующим релизом необходимо увеличить `versionCode` и `versionName` в `android/app/build.gradle.kts`.

## Независимая проверка скачанного release

После скачивания четырех файлов GitHub Release выполните проверку отдельно от workflow. Нужны Android Build Tools (`apksigner`) и JDK (`jarsigner`):

```bash
APKSIGNER=$(find "$ANDROID_HOME/build-tools" -type f -name apksigner | sort -V | tail -1)

python scripts/verify_android_release.py \
  --apk ceh-sklad-0.4.0.apk \
  --aab ceh-sklad-0.4.0.aab \
  --manifest android-release-manifest.json \
  --checksums SHA256SUMS.txt \
  --apksigner "$APKSIGNER" \
  --expected-api-base-url https://sklad.example.ru/ \
  --expected-source-commit <40-символьный-SHA>
```

Verifier проверяет:

- SHA-256 и размер APK относительно manifest;
- SHA256SUMS для APK/AAB/manifest и отсутствие неожиданных файлов в списке;
- криптографическую подпись APK;
- SHA-256 сертификата подписи относительно manifest;
- подпись AAB;
- `application_id=ru.ceh.sklad`, versionCode/versionName;
- production API URL и source commit при передаче ожидаемых значений.

Успешный результат содержит `"status": "verified"` и вычисленные SHA/fingerprint без секретов.

## Перед production-публикацией

1. Создать production signing key helper-скриптом и сохранить офлайн backup.
2. Убедиться, что четыре `CEH_ANDROID_*` GitHub Secrets настроены.
3. Развернуть backend на фактическом HTTPS-домене и получить зеленый общий CI на release commit.
4. Запустить workflow `Подписанный Android release` с production HTTPS origin.
5. Скачать APK/AAB/manifest/SHA256SUMS из GitHub Release и независимо выполнить verifier.
6. Установить/обновить подписанный APK на физическом устройстве.
7. Пройти login, остатки, retail/wholesale sale, возврат, сдачу денег и offline queue.
8. Не менять signing key между обновлениями приложения.
