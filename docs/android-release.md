# Подписанная Android release-сборка

Release-контур Android не хранит keystore, alias или пароли в Git. Gradle получает все параметры подписи только из переменных окружения, а GitHub Actions — из GitHub Secrets.

## Обязательные параметры Gradle

Для любой release-задачи (`assembleRelease`, `bundleRelease` и аналогичных) должны быть заданы:

```text
CEH_ANDROID_API_BASE_URL=https://sklad.example.ru/
CEH_ANDROID_KEYSTORE_FILE=/secure/path/ceh-sklad-upload.jks
CEH_ANDROID_KEYSTORE_PASSWORD=<пароль keystore>
CEH_ANDROID_KEY_ALIAS=<alias ключа>
CEH_ANDROID_KEY_PASSWORD=<пароль ключа>
```

Дополнительно можно переопределить версию:

```text
CEH_ANDROID_VERSION_NAME=1.0.0
CEH_ANDROID_VERSION_CODE=10
```

`CEH_ANDROID_API_BASE_URL` для release обязан начинаться с `https://`. Если URL подписи или любой обязательный параметр отсутствует, Gradle завершает release-сборку с ошибкой до создания APK/AAB.

Debug-сборка по-прежнему использует `http://10.0.2.2:8000/` и отдельный debug-manifest, разрешающий локальный cleartext HTTP только для эмулятора.

## Локальная сборка

Пример для Linux/macOS:

```bash
export CEH_ANDROID_API_BASE_URL="https://sklad.example.ru/"
export CEH_ANDROID_KEYSTORE_FILE="$HOME/.keys/ceh-sklad-upload.jks"
export CEH_ANDROID_KEYSTORE_PASSWORD="..."
export CEH_ANDROID_KEY_ALIAS="ceh-upload"
export CEH_ANDROID_KEY_PASSWORD="..."
export CEH_ANDROID_VERSION_NAME="1.0.0"
export CEH_ANDROID_VERSION_CODE="10"

cd android
gradle :app:assembleRelease :app:bundleRelease
```

Результаты:

```text
android/app/build/outputs/apk/release/app-release.apk
android/app/build/outputs/bundle/release/app-release.aab
```

Keystore и файлы `*.jks`, `*.keystore`, `keystore.properties`, `signing.properties` исключены из Git. Не храните секреты в `gradle.properties`, если этот файл может попасть в общий репозиторий или резервную копию без шифрования.

## GitHub Secrets

Для ручного workflow `.github/workflows/android-release.yml` настройте в репозитории четыре секрета:

```text
CEH_ANDROID_KEYSTORE_BASE64
CEH_ANDROID_KEYSTORE_PASSWORD
CEH_ANDROID_KEY_ALIAS
CEH_ANDROID_KEY_PASSWORD
```

`CEH_ANDROID_KEYSTORE_BASE64` содержит base64-представление бинарного keystore. Например:

```bash
base64 -w 0 ceh-sklad-upload.jks
```

На macOS:

```bash
base64 < ceh-sklad-upload.jks | tr -d '\n'
```

Сам файл keystore в репозиторий не добавляется.

## Ручной GitHub Actions release

Workflow **«Сборка подписанного Android release»** запускается только вручную (`workflow_dispatch`) и принимает:

- HTTPS-адрес production backend;
- `versionName`;
- `versionCode`.

Workflow:

1. проверяет HTTPS URL, versionCode и наличие всех signing secrets;
2. восстанавливает временный keystore в `$RUNNER_TEMP`;
3. собирает `assembleRelease` и `bundleRelease`;
4. проверяет APK через `apksigner`;
5. проверяет AAB через `jarsigner`;
6. рассчитывает SHA-256 обоих файлов;
7. публикует APK, AAB и файл контрольных сумм как GitHub Actions artifact на 14 дней.

Keystore существует только на временном диске runner во время job.

## CI-проверка без production-ключа

Обычный Android CI генерирует одноразовый тестовый keystore, собирает release APK с `https://example.invalid/` и проверяет его подпись через `apksigner`. Это проверяет Gradle signing-конфигурацию на каждом push, не раскрывая production-ключ.

Тестовый CI-ключ нельзя использовать для реальных установочных сборок или публикации.

## Ключ публикации

Для публикации в Google Play рекомендуется использовать Play App Signing и отдельный upload key. Ключ и его пароли должны храниться вне репозитория в защищенном хранилище; потеря ключа или компрометация секретов требует отдельной процедуры ротации/восстановления со стороны выбранного канала распространения.
