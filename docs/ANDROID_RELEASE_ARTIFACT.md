# Проверяемый Android release

Ручной workflow `Подписанный Android release` формирует проверяемый пакет и после всех release-gates публикует его как постоянный GitHub Release с уникальным tag `android-v<versionName>`.

## Файлы релиза

GitHub Release содержит:

- `ceh-sklad-<version>.apk` — подписанный APK;
- `ceh-sklad-<version>.aab` — подписанный Android App Bundle;
- `android-release-manifest.json` — несекретный manifest сборки;
- `SHA256SUMS.txt` — SHA-256 APK, AAB и manifest.

Тот же набор временно сохраняется как Actions artifact для диагностики. Источником распространения production-сборки является GitHub Release.

## Что содержит manifest

- SHA-256 и размер APK;
- SHA-256 сертификата подписи;
- `application_id`;
- `version_code` и `version_name`;
- production API base URL, зашитый в build — для текущей схемы `https://IP:PORT/`;
- SHA исходного Git commit;
- время формирования manifest в UTC.

Keystore и пароли в manifest/Release не записываются.

## Автоматическая перепроверка до публикации

Workflow выполняет:

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

Публикация блокируется при повреждении файлов, другом SHA/signing certificate, неверном `https://IP:PORT/` или другом source commit.

## Независимая проверка после скачивания

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

Verifier проверяет SHA/размеры, APK/AAB signatures, signer fingerprint, package/version, production API URL и source commit.

## Безопасность workflow

- release разрешён только с текущего HEAD `main`;
- на том же SHA должны быть зелёными оба обязательных CI gate;
- production backend проверяется **до** декодирования keystore по HTTPS readiness, версии и Alembic head;
- `api_base_url` допускается только как HTTPS origin без credentials/path/query/fragment; IP + custom port поддерживаются;
- release-contract тесты повторно запускаются до signing;
- существующий `android-v<versionName>` не перезаписывается;
- временный keystore удаляется через `always()`;
- production signing key не хранится в Git и не ротируется между обычными обновлениями.

Подготовка signing key и GitHub Secrets описана в `docs/ANDROID_RELEASE.md`.
