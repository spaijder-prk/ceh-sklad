from __future__ import annotations

import json
import re
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "android-release.yml"
ANDROID_BUILD_PATH = REPO_ROOT / "android" / "app" / "build.gradle.kts"
BACKEND_PYPROJECT_PATH = REPO_ROOT / "backend" / "pyproject.toml"
BACKEND_VERSION_PATH = REPO_ROOT / "backend" / "app" / "version.py"
BACKEND_MAIN_PATH = REPO_ROOT / "backend" / "app" / "main.py"
WEB_PACKAGE_PATH = REPO_ROOT / "admin-web" / "package.json"
PRODUCT_VERSION_PATH = REPO_ROOT / "VERSION"


class AndroidReleaseContractTests(unittest.TestCase):
    def test_release_workflow_preserves_signing_and_immutability_contract(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        required_fragments = (
            "permissions:\n  contents: write\n  actions: read",
            "concurrency:\n  group: android-production-release\n  cancel-in-progress: false",
            "actions/setup-python@v5",
            'python-version: "3.12"',
            "refs/heads/main",
            "git/ref/heads/main",
            "Проверка проекта",
            "Проверка release-контрактов",
            "PROJECT_CI_COUNT",
            "RELEASE_CONTRACT_CI_COUNT",
            'python -m unittest discover -s scripts/tests -p "test_*.py" -v',
            ":app:assembleRelease",
            ":app:bundleRelease",
            "apksigner",
            "--print-certs",
            "jarsigner -verify",
            "android_release_manifest.py",
            "verify_android_release.py",
            "Перепроверить подготовленные файлы релиза",
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

    def test_product_versions_are_synchronized(self) -> None:
        product_version = PRODUCT_VERSION_PATH.read_text(encoding="utf-8").strip()
        self.assertRegex(product_version, r"^\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.-]+)?$")

        backend = tomllib.loads(BACKEND_PYPROJECT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(backend["project"]["version"], product_version)

        backend_version = BACKEND_VERSION_PATH.read_text(encoding="utf-8")
        backend_match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', backend_version)
        self.assertIsNotNone(backend_match)
        self.assertEqual(backend_match.group(1), product_version)

        backend_main = BACKEND_MAIN_PATH.read_text(encoding="utf-8")
        self.assertIn("version=APP_VERSION", backend_main)
        self.assertIn('"version": APP_VERSION', backend_main)

        web = json.loads(WEB_PACKAGE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(web["version"], product_version)

        build = ANDROID_BUILD_PATH.read_text(encoding="utf-8")
        version_code_match = re.search(r"versionCode\s*=\s*(\d+)", build)
        version_name_match = re.search(r'versionName\s*=\s*"([^"]+)"', build)
        self.assertIsNotNone(version_code_match)
        self.assertIsNotNone(version_name_match)
        self.assertGreater(int(version_code_match.group(1)), 0)
        self.assertEqual(version_name_match.group(1), product_version)


if __name__ == "__main__":
    unittest.main()
