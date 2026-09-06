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


def test_android_instrumented_workflow_checks_full_pull_request_diff():
    workflow = (ROOT / ".github/workflows/android-instrumented.yml").read_text(encoding="utf-8")

    assert "fetch-depth: 0" in workflow
    assert "github.event.pull_request.base.sha" in workflow
    assert "github.event.pull_request.head.sha" in workflow
    assert 'git diff --quiet "$BASE_SHA" "$HEAD_SHA" -- android .github/workflows/android-instrumented.yml' in workflow
    assert "run_smoke=false" in workflow
    assert "run_smoke=true" in workflow
    assert "if: needs.changes.outputs.run_smoke == 'true'" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "HEAD^ HEAD" not in workflow


def test_android_release_workflow_keeps_manifest_and_removes_keystore():
    workflow = (ROOT / ".github/workflows/android-release.yml").read_text(encoding="utf-8")

    assert "scripts/android_release_manifest.py" in workflow
    assert "android-release-manifest.json" in workflow
    assert "apksigner" in workflow
    assert "if: ${{ always() }}" in workflow
    assert 'rm -f "$RUNNER_TEMP/ceh-sklad-release.keystore"' in workflow
    assert "CEH_ANDROID_KEYSTORE_BASE64" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "./android/gradlew -p android" in workflow


def test_android_workflows_use_current_java_setup_action():
    workflows = [
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
        (ROOT / ".github/workflows/android-release.yml").read_text(encoding="utf-8"),
        (ROOT / ".github/workflows/android-instrumented.yml").read_text(encoding="utf-8"),
    ]

    for workflow in workflows:
        assert "actions/setup-java@v4" not in workflow
        assert "actions/setup-java@v5" in workflow


def test_main_ci_checks_full_change_range_before_skipping_android():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "android-changes:" in workflow
    assert "fetch-depth: 0" in workflow
    assert "github.event.pull_request.base.sha" in workflow
    assert "github.event.before" in workflow
    assert 'git diff --quiet "$BASE_SHA" "$HEAD_SHA" -- android .github/workflows/ci.yml' in workflow
    assert 'echo "run_android=false" >> "$GITHUB_OUTPUT"' in workflow
    assert 'echo "run_android=true" >> "$GITHUB_OUTPUT"' in workflow
    assert "needs: android-changes" in workflow
    assert "if: needs.android-changes.outputs.run_android == 'true'" in workflow
    assert "HEAD^ HEAD" not in workflow
