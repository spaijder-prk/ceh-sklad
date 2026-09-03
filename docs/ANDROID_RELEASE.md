# Сборка Android для тестирования и production

## Debug

Debug-сборка предназначена для Android Emulator и обращается к backend по адресу `http://10.0.2.2:8000/`. Только debug-манифест разрешает незашифрованный HTTP.

```bash
gradle -p android :app:assembleDebug
```

В GitHub Actions готовый `app-debug.apk` сохраняется как артефакт `ceh-sklad-debug-apk`.

## Release

Release-сборка запрещает cleartext HTTP. URL backend передается Gradle-свойством `CEH_API_BASE_URL` и для рабочего окружения должен быть HTTPS-адресом с доступным сертификатом.

```bash
gradle -p android :app:assembleRelease \
  -PCEH_API_BASE_URL=https://sklad.example.ru/
```

Если свойство не передано, APK получает заведомо нерабочий адрес `https://not-configured.invalid/`, чтобы тестовая конфигурация не могла случайно обратиться к локальному backend.

## Перед публикацией

Для production необходимо отдельно настроить release signing через защищенные GitHub Secrets/CI и не хранить keystore или его пароль в репозитории. Также нужно использовать HTTPS reverse proxy перед FastAPI и ограничить CORS/сетевой доступ под фактические домены.
