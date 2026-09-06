from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "deploy_production.py"

spec = importlib.util.spec_from_file_location("deploy_production", SCRIPT_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DeployProductionTests(unittest.TestCase):
    def test_parse_env_and_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env.production"
            path.write_text(
                "# comment\nCEH_DOMAIN=sklad.example.org\nAPP_NAME='Цех Склад'\n",
                encoding="utf-8",
            )
            values = module.parse_env_file(path)
        self.assertEqual(values["CEH_DOMAIN"], "sklad.example.org")
        self.assertEqual(values["APP_NAME"], "Цех Склад")
        self.assertEqual(module.validate_domain(values["CEH_DOMAIN"]), "sklad.example.org")

    def test_domain_rejects_test_values(self) -> None:
        for value in ("localhost", "https://sklad.example.org", "ci.invalid", "example.com"):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                module.validate_domain(value)

    def test_compose_command_is_pinned_to_production_files(self) -> None:
        self.assertEqual(
            module.compose_command("config", "--quiet"),
            [
                "docker",
                "compose",
                "--env-file",
                ".env.production",
                "-f",
                "docker-compose.production.yml",
                "config",
                "--quiet",
            ],
        )

    @unittest.skipUnless(os.name == "posix", "Проверка chmod применима только к POSIX")
    def test_env_permissions_reject_group_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env.production"
            path.write_text("CEH_DOMAIN=sklad.example.org\n", encoding="utf-8")
            path.chmod(0o640)
            with self.assertRaises(RuntimeError):
                module.validate_env_permissions(path)
            path.chmod(0o600)
            module.validate_env_permissions(path)

    def test_wait_for_readiness_checks_version_and_schema(self) -> None:
        responses = [
            {"status": "ok", "version": "0.4.0"},
            {
                "status": "ready",
                "database": "ok",
                "version": "0.4.0",
                "schema_revision": "20260904_09",
            },
        ]
        with mock.patch.object(module, "_get_json", side_effect=responses):
            ready = module.wait_for_readiness("sklad.example.org", "0.4.0", 1.0)
        self.assertEqual(ready["schema_revision"], "20260904_09")

    def test_wait_for_readiness_rejects_wrong_version(self) -> None:
        responses = [
            {"status": "ok", "version": "0.3.9"},
            {
                "status": "ready",
                "database": "ok",
                "version": "0.3.9",
                "schema_revision": "20260904_09",
            },
        ]
        with mock.patch.object(module, "_get_json", side_effect=responses), mock.patch.object(
            module.time, "sleep", return_value=None
        ), mock.patch.object(module.time, "monotonic", side_effect=[0.0, 0.0, 2.0]):
            with self.assertRaises(RuntimeError):
                module.wait_for_readiness("sklad.example.org", "0.4.0", 1.0)


if __name__ == "__main__":
    unittest.main()
