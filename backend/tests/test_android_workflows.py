from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_android_instrumented_workflow_keeps_diagnostics_on_failure():
    workflow = (ROOT / ".github/workflows/android-instrumented.yml").read_text(encoding="utf-8")

    assert "permissions:\n  contents: read" in workflow
    assert "adb logcat -d" in workflow
    assert "adb exec-out screencap -p" in workflow
    assert "androidTest-results/connected/**" in workflow
    assert "reports/androidTests/connected/**" in workflow
    assert "if: ${{ always() }}" in workflow
    assert "actions/upload-artifact@v4" in workflow


def test_android_release_workflow_keeps_manifest_and_removes_keystore():
    workflow = (ROOT / ".github/workflows/android-release.yml").read_text(encoding="utf-8")

    assert "scripts/android_release_manifest.py" in workflow
    assert "android-release-manifest.json" in workflow
    assert "apksigner" in workflow
    assert "if: ${{ always() }}" in workflow
    assert 'rm -f "$RUNNER_TEMP/ceh-sklad-release.keystore"' in workflow
    assert "CEH_ANDROID_KEYSTORE_BASE64" in workflow
    assert "actions/upload-artifact@v4" in workflow
