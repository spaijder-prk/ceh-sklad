from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_browser_does_not_persist_or_put_jwt_into_websocket_url():
    app = (ROOT / "admin-web/src/App.tsx").read_text(encoding="utf-8")

    assert "localStorage.setItem('ceh-token'" not in app
    assert "localStorage.getItem('ceh-token'" not in app
    assert "realtime?token=" not in app
    assert "/auth/web-login" in app
    assert "credentials: 'include'" in app


def test_android_websocket_uses_authorization_header_not_query_token():
    repository = (
        ROOT / "android/app/src/main/java/ru/ceh/sklad/data/WarehouseRepository.kt"
    ).read_text(encoding="utf-8")

    assert "realtime?token=" not in repository
    assert '.header("Authorization", "Bearer $currentToken")' in repository


def test_android_local_secrets_use_keystore_and_backup_is_disabled():
    storage = (ROOT / "android/app/src/main/java/ru/ceh/sklad/data/AppStorage.kt").read_text(encoding="utf-8")
    manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    build = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")

    assert "AndroidKeyStore" in storage
    assert "AES/GCM/NoPadding" in storage
    assert "EncryptedSharedPreferences" not in storage
    assert 'android:allowBackup="false"' in manifest
    assert "androidx.security:security-crypto" not in build
