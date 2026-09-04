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


def test_android_instrumented_workflow_runs_emulator_only_for_latest_android_change():
    workflow = (ROOT / ".github/workflows/android-instrumented.yml").read_text(encoding="utf-8")

    assert "fetch-depth: 2" in workflow
    assert "github.event.pull_request.head.sha || github.sha" in workflow
    assert "git diff --quiet HEAD^ HEAD -- android .github/workflows/android-instrumented.yml" in workflow
    assert "run_smoke=false" in workflow
    assert "run_smoke=true" in workflow
    assert "if: needs.changes.outputs.run_smoke == 'true'" in workflow
    assert "cancel-in-progress: true" in workflow


def test_android_release_workflow_keeps_manifest_and_removes_keystore():
    workflow = (ROOT / ".github/workflows/android-release.yml").read_text(encoding="utf-8")

    assert "scripts/android_release_manifest.py" in workflow
    assert "android-release-manifest.json" in workflow
    assert "apksigner" in workflow
    assert "if: ${{ always() }}" in workflow
    assert 'rm -f "$RUNNER_TEMP/ceh-sklad-release.keystore"' in workflow
    assert "CEH_ANDROID_KEYSTORE_BASE64" in workflow
    assert "actions/upload-artifact@v4" in workflow


def test_android_workflows_use_current_java_setup_action():
    workflows = [
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
        (ROOT / ".github/workflows/android-release.yml").read_text(encoding="utf-8"),
        (ROOT / ".github/workflows/android-instrumented.yml").read_text(encoding="utf-8"),
    ]

    for workflow in workflows:
        assert "actions/setup-java@v4" not in workflow
        assert "actions/setup-java@v5" in workflow
