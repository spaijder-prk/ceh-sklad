from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_DIR.parent
SCRIPT_PATH = SCRIPTS_DIR / "verify_release_backend.py"

spec = importlib.util.spec_from_file_location("verify_release_backend", SCRIPT_PATH)
assert spec and spec.loader
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class VerifyReleaseBackendTests(unittest.TestCase):
    def test_expected_contract_matches_repository(self) -> None:
        self.assertEqual(verify.expected_version(REPO_ROOT), "0.4.0")
        self.assertEqual(verify.expected_schema_revision(REPO_ROOT), "20260904_09")

    def test_ready_payload_requires_exact_version_and_schema(self) -> None:
        payload = {
            "status": "ready",
            "database": "ok",
            "schema_revision": "20260904_09",
            "version": "0.4.0",
        }
        result = verify.verify_ready_payload(
            payload,
            expected_version_value="0.4.0",
            expected_schema_revision_value="20260904_09",
        )
        self.assertEqual(result[-1], ())

        drift = dict(payload, version="0.3.9", schema_revision="20260903_08")
        drift_result = verify.verify_ready_payload(
            drift,
            expected_version_value="0.4.0",
            expected_schema_revision_value="20260904_09",
        )
        self.assertTrue(any("backend version не совпадает" in error for error in drift_result[-1]))
        self.assertTrue(any("schema_revision не совпадает" in error for error in drift_result[-1]))

    def test_release_url_is_https_origin_only(self) -> None:
        self.assertEqual(verify.validate_base_url("https://sklad.example.ru/"), "https://sklad.example.ru")
        for value in (
            "http://sklad.example.ru",
            "https://user:pass@sklad.example.ru",
            "https://sklad.example.ru/api",
            "https://sklad.example.ru/?x=1",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                verify.validate_base_url(value)


if __name__ == "__main__":
    unittest.main()
