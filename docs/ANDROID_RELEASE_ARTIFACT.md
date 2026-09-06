# Проверяемый Android release

Ручной workflow `Подписанный Android release` после всех release-gates публикует постоянный GitHub Release с уникальным tag `android-v<versionName>`.

## Файлы релиза

GitHub Release содержит:

- `ceh-sklad-<version>.apk` — подписанный APK;
- `ceh-sklad-<version>.aab` — подписанный Android App Bundle;
- `android-release-manifest.json` — несекретный manifest сборки;
- `ceh-sklad-root-ca.crt` — публичный root certificate внутреннего Caddy CA;
- `SHA256SUMS.txt` — SHA-256 всех четырёх файлов выше.

Root certificate не содержит private key. Private CA key остаётся только в production `caddy_data` и его закрытом PKI backup.

## Manifest

Manifest фиксирует:

- SHA-256 и размер APK;
- SHA-256 сертификата подписи APK;
- `application_id`;
- `version_code`/`version_name`;
- точный production API URL `https://IP:PORT/`;
- source Git commit;
- UTC-время формирования.

## Автоматическая перепроверка

До публикации workflow выполняет:

```bash
python scripts/verify_android_release.py \
  --apk "$RELEASE_DIR/ceh-sklad-${VERSION_NAME}.apk" \
  --aab "$RELEASE_DIR/ceh-sklad-${VERSION_NAME}.aab" \
  --manifest "$RELEASE_DIR/android-release-manifest.json" \
  --ca-cert "$RELEASE_DIR/ceh-sklad-root-ca.crt" \
  --checksums "$RELEASE_DIR/SHA256SUMS.txt" \
  --apksigner "$APKSIGNER" \
  --expected-api-base-url "$API_BASE_URL" \
  --expected-source-commit "$GITHUB_SHA"
```

Verifier требует точный набор checksum-файлов и блокирует публикацию при повреждённом APK/AAB/manifest/root CA, другом signer certificate, неверном `IP:PORT` или source commit.

## Независимая проверка после скачивания

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

Перед установкой root CA на Android/рабочий компьютер дополнительно сравните его SHA-256 fingerprint со значением, полученным напрямую на production server командой `python3 scripts/export_internal_ca.py`.

## Безопасность workflow

- release разрешён только с текущего HEAD `main`;
- на том же SHA должны быть зелёными оба обязательных CI gate;
- `CEH_INTERNAL_CA_CERT_BASE64` содержит только публичный root certificate;
- production backend проверяется через этот CA **до декодирования keystore**;
- exact HTTPS readiness/version/Alembic head обязательны;
- HTTP и отключение TLS verification не используются;
- существующий `android-v<versionName>` не перезаписывается;
- временные keystore/root CA удаляются через `always()`;
- production signing key и Caddy CA private key не хранятся в Git.

Подготовка signing key, root CA и GitHub Secrets описана в `docs/ANDROID_RELEASE.md`.
