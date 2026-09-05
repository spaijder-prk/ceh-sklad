from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "android-release.yml"
ANDROID_BUILD_PATH = REPO_ROOT / "android" / "app" / "build.gradle.kts"


class AndroidReleaseContractTests(unittest.TestCase):
    def test_release_workflow_preserves_signing_and_immutability_contract(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        required_fragments = (
            "permissions:\n  contents: write\n  actions: read",
            "actions/setup-python@v5",
            'python-version: "3.12"',
            "refs/heads/main",
            "git/ref/heads/main",
            "Проверка проекта",
            'python -m unittest discover -s scripts/tests -p "test_*.py" -v',
            ":app:assembleRelease",
            ":app:bundleRelease",
            "apksigner",
            "--print-certs",
            "jarsigner -verify",
            "android_release_manifest.py",
            "sha256sum",
            "gh release view",
            "gh release create",
            '--target "$GITHUB_SHA"',
            "android-v${VERSION_NAME}",
            "if: ${{ always() }}",
            'rm -f "$RUNNER_TEMP/ceh-sklad-release.keystore"',
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, workflow)

        self.assertNotIn("--clobber", workflow)
        self.assertIn("CEH_ANDROID_KEYSTORE_BASE64", workflow)
        self.assertIn("CEH_ANDROID_KEYSTORE_PASSWORD", workflow)
        self.assertIn("CEH_ANDROID_KEY_ALIAS", workflow)
        self.assertIn("CEH_ANDROID_KEY_PASSWORD", workflow)
        self.assertIn("api_base_url", workflow)
        self.assertIn("parsed.scheme != 'https'", workflow)

    def test_android_version_is_releaseable(self) -> None:
        build = ANDROID_BUILD_PATH.read_text(encoding="utf-8")
        version_code_match = re.search(r"versionCode\s*=\s*(\d+)", build)
        version_name_match = re.search(r'versionName\s*=\s*"([^"]+)"', build)

        self.assertIsNotNone(version_code_match)
        self.assertIsNotNone(version_name_match)

        version_code = int(version_code_match.group(1))
        version_name = version_name_match.group(1)

        self.assertGreater(version_code, 0)
        self.assertRegex(version_name, r"^\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.-]+)?$")
        self.assertNotIn("SNAPSHOT", version_name.upper())


if __name__ == "__main__":
    unittest.main()
