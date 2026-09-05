# Сборка Android для тестирования и production

## Debug

Debug-сборка предназначена для Android Emulator и обращается к backend по адресу `http://10.0.2.2:8000/`. Только debug-манифест разрешает незашифрованный HTTP.

```bash
gradle -p android :app:assembleDebug
```

В обычном CI готовый `app-debug.apk` сохраняется как артефакт `ceh-sklad-debug-apk`. CI также компилирует release-вариант с тестовым HTTPS URL без подписи, чтобы release-конфигурация не ломалась незаметно.

## Release URL

Release-сборка запрещает cleartext HTTP. URL backend передается Gradle-свойством `CEH_API_BASE_URL` и для рабочего окружения должен быть HTTPS-адресом с доступным сертификатом.

```bash
gradle -p android :app:assembleRelease \
  -PCEH_API_BASE_URL=https://sklad.example.ru/
```

Если свойство не передано, APK получает заведомо нерабочий адрес `https://not-configured.invalid/`, чтобы тестовая конфигурация не могла случайно обратиться к локальному backend.

## Release signing

Gradle подключает release signing только если одновременно заданы четыре переменные окружения:

```text
CEH_ANDROID_KEYSTORE_PATH
CEH_ANDROID_KEYSTORE_PASSWORD
CEH_ANDROID_KEY_ALIAS
CEH_ANDROID_KEY_PASSWORD
```

Keystore и пароли нельзя хранить в репозитории.

Для GitHub Actions подготовлен ручной workflow `Подписанный Android release`. В настройках репозитория ему нужны Secrets:

```text
CEH_ANDROID_KEYSTORE_BASE64
CEH_ANDROID_KEYSTORE_PASSWORD
CEH_ANDROID_KEY_ALIAS
CEH_ANDROID_KEY_PASSWORD
```

`CEH_ANDROID_KEYSTORE_BASE64` — содержимое keystore, закодированное base64. Workflow проверяет HTTPS URL, декодирует keystore во временный каталог runner, собирает release, проверяет APK через `apksigner` и сохраняет подписанный APK как артефакт на 14 дней.

## Перед production-публикацией

1. Создать отдельный production keystore и сохранить его резервную копию вне GitHub.
2. Добавить перечисленные secrets в защищенное окружение/репозиторий GitHub.
3. Запустить workflow `Подписанный Android release`, указав рабочий HTTPS URL backend.
4. Проверить полученный APK на тестовом устройстве до распространения.
5. Не менять signing key между обновлениями приложения.
