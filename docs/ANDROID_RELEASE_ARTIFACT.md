# Проверяемый Android release

Ручной workflow `Подписанный Android release` формирует проверяемый пакет и после всех release-gates публикует его как постоянный GitHub Release с уникальным tag `android-v<versionName>`.

## Файлы релиза

GitHub Release содержит четыре файла:

- `ceh-sklad-<version>.apk` — подписанный APK для установки на Android-устройства;
- `ceh-sklad-<version>.aab` — подписанный Android App Bundle;
- `android-release-manifest.json` — несекретный manifest сборки;
- `SHA256SUMS.txt` — SHA-256 APK, AAB и manifest.

Дополнительно тот же набор временно сохраняется как GitHub Actions artifact `ceh-sklad-release-<version>` для диагностики конкретного workflow run. Источником распространения production-сборки является GitHub Release, а не временный Actions artifact.

## Что содержит manifest

- SHA-256 и размер APK;
- SHA-256 сертификата подписи из `apksigner verify --print-certs`;
- `application_id`;
- `version_code` и `version_name` из Gradle `output-metadata.json`;
- production API base URL, зашитый в release build;
- SHA исходного Git commit;
- время формирования manifest в UTC.

Keystore, пароль keystore, key password и другие release secrets в manifest/Release не записываются.

## Автоматическая перепроверка до публикации

После сборки и копирования файлов в итоговый release-каталог workflow выполняет:

```bash
python scripts/verify_android_release.py \
  --apk "$RELEASE_DIR/ceh-sklad-${VERSION_NAME}.apk" \
  --aab "$RELEASE_DIR/ceh-sklad-${VERSION_NAME}.aab" \
  --manifest "$RELEASE_DIR/android-release-manifest.json" \
  --checksums "$RELEASE_DIR/SHA256SUMS.txt" \
  --apksigner "$APKSIGNER" \
  --expected-api-base-url "$API_BASE_URL" \
  --expected-source-commit "$GITHUB_SHA"
```

Публикация не выполняется, если verifier обнаруживает повреждение файлов, несовпадение SHA, другой сертификат подписи, неверный production URL или другой source commit.

## Независимая проверка после скачивания

После скачивания GitHub Release рекомендуется повторить verifier уже на другой машине:

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

Успешная проверка возвращает JSON со `status=verified`, вычисленными SHA APK/AAB и fingerprint сертификата без каких-либо секретов.

Verifier проверяет одновременно:

- SHA-256 и размер APK относительно manifest;
- SHA256SUMS для APK, AAB и manifest;
- отсутствие неожиданных записей в SHA256SUMS;
- криптографическую подпись APK через `apksigner`;
- SHA-256 сертификата APK относительно manifest;
- подпись AAB через `jarsigner`;
- `application_id=ru.ceh.sklad` и корректную версию;
- ожидаемые production API URL и source commit.

## Безопасность workflow

- release разрешён только с текущего HEAD `main`;
- на этом же SHA должен уже существовать завершённый зелёный workflow `Проверка проекта`;
- одновременно выполняется не более одного production Android release;
- API URL допускается только как HTTPS origin без credentials/path/query/fragment;
- release-contract тесты повторно запускаются перед использованием signing secrets;
- APK и AAB проверяются до упаковки, затем итоговый пакет проверяется ещё раз независимым verifier;
- существующий `android-v<versionName>` не перезаписывается: для нового релиза требуется новая версия;
- временный keystore удаляется шагом `always()`;
- production signing key не хранится в Git и не должен ротироваться между обычными обновлениями приложения.

Подготовка production signing key и GitHub Secrets описана в `docs/ANDROID_RELEASE.md`.
