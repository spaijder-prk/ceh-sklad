# Проверяемый Android release artifact

Ручной workflow `Подписанный Android release` формирует один artifact `ceh-sklad-release-apk` с двумя файлами:

- `app-release.apk` — подписанный release APK;
- `android-release-manifest.json` — несекретный manifest сборки.

## Что содержит manifest

- SHA-256 APK;
- размер APK;
- SHA-256 сертификата подписи из `apksigner verify --print-certs`;
- `applicationId`;
- `versionCode` и `versionName` из Gradle `output-metadata.json`;
- production API base URL, зашитый в release build;
- SHA исходного Git commit;
- время формирования manifest в UTC.

Keystore, alias password и другие release secrets в manifest/artifact не записываются.

## Проверка после скачивания

```bash
sha256sum app-release.apk
cat android-release-manifest.json
```

Хэш APK должен совпадать с `artifact_sha256`. Для независимой проверки сертификата:

```bash
apksigner verify --print-certs app-release.apk
```

`Signer #1 certificate SHA-256 digest` должен совпадать с `signer_certificate_sha256` в manifest.

Перед установкой также сверяются `application_id=ru.ceh.sklad`, версия и `api_base_url`.

## Безопасность workflow

- API URL допускается только как HTTPS origin без credentials/path/query/fragment;
- APK проверяется `apksigner verify --verbose` до формирования manifest;
- временный keystore удаляется шагом `always()` после сборки;
- GitHub artifact хранится 14 дней;
- фактические signing secrets должны находиться только в GitHub Actions Secrets.
