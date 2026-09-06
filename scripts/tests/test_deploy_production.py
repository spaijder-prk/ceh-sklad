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
    def test_parse_env_and_public_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env.production"
            path.write_text(
                "# comment\n"
                "CEH_PUBLIC_IP=93.184.216.34\n"
                "CEH_PUBLIC_HOST=93.184.216.34\n"
                "CEH_PUBLIC_PORT=40443\n"
                "CEH_PUBLIC_ORIGIN=https://93.184.216.34:40443\n"
                "CEH_PUBLIC_WS_ORIGIN=wss://93.184.216.34:40443\n"
                "CEH_TLS_MODE=internal-ca\n"
                "APP_NAME='Цех Склад'\n",
                encoding="utf-8",
            )
            values = module.parse_env_file(path)
        self.assertEqual(values["APP_NAME"], "Цех Склад")
        self.assertEqual(
            module.validate_public_endpoint(values),
            ("93.184.216.34", 40443, "https://93.184.216.34:40443"),
        )

    def test_public_endpoint_rejects_private_ip_drift_and_wrong_tls_mode(self) -> None:
        private_env = {
            "CEH_PUBLIC_IP": "192.168.1.10",
            "CEH_PUBLIC_HOST": "192.168.1.10",
            "CEH_PUBLIC_PORT": "40443",
            "CEH_PUBLIC_ORIGIN": "https://192.168.1.10:40443",
            "CEH_PUBLIC_WS_ORIGIN": "wss://192.168.1.10:40443",
            "CEH_TLS_MODE": "internal-ca",
        }
        with self.assertRaisesRegex(RuntimeError, "публичным"):
            module.validate_public_endpoint(private_env)

        drift_env = {
            "CEH_PUBLIC_IP": "93.184.216.34",
            "CEH_PUBLIC_HOST": "93.184.216.34",
            "CEH_PUBLIC_PORT": "40443",
            "CEH_PUBLIC_ORIGIN": "https://93.184.216.34:44443",
            "CEH_PUBLIC_WS_ORIGIN": "wss://93.184.216.34:40443",
            "CEH_TLS_MODE": "internal-ca",
        }
        with self.assertRaisesRegex(RuntimeError, "CEH_PUBLIC_ORIGIN"):
            module.validate_public_endpoint(drift_env)

        wrong_tls = dict(drift_env)
        wrong_tls["CEH_PUBLIC_ORIGIN"] = "https://93.184.216.34:40443"
        wrong_tls["CEH_TLS_MODE"] = "acme"
        with self.assertRaisesRegex(RuntimeError, "CEH_TLS_MODE"):
            module.validate_public_endpoint(wrong_tls)

    def test_public_port_accepts_nonstandard_and_standard_ports(self) -> None:
        self.assertEqual(module.validate_public_port("40443"), 40443)
        self.assertEqual(module.validate_public_port("80"), 80)
        for value in ("0", "65536", "abc"):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                module.validate_public_port(value)

    def test_ipv6_origin_uses_brackets(self) -> None:
        self.assertEqual(
            module.public_origins("2606:4700:4700::1111", 40443),
            ("https://[2606:4700:4700::1111]:40443", "wss://[2606:4700:4700::1111]:40443"),
        )

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
            path.write_text("CEH_PUBLIC_IP=93.184.216.34\n", encoding="utf-8")
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
        with mock.patch.object(module.ssl, "create_default_context", return_value=object()), mock.patch.object(
            module, "_get_json", side_effect=responses
        ):
            ready = module.wait_for_readiness(
                "https://93.184.216.34:40443", "0.4.0", 1.0, "TEST ROOT CA"
            )
        self.assertEqual(ready["schema_revision"], "20260904_09")

    def test_wait_for_readiness_reports_database_state(self) -> None:
        responses = [
            {"status": "ok", "version": "0.4.0"},
            {
                "status": "starting",
                "database": "down",
                "version": "0.4.0",
                "schema_revision": "20260904_09",
            },
        ]
        with mock.patch.object(module.ssl, "create_default_context", return_value=object()), mock.patch.object(
            module, "_get_json", side_effect=responses
        ), mock.patch.object(module.time, "sleep", return_value=None), mock.patch.object(
            module.time, "monotonic", side_effect=[0.0, 0.0, 2.0]
        ):
            with self.assertRaisesRegex(RuntimeError, "database='down'"):
                module.wait_for_readiness(
                    "https://93.184.216.34:40443", "0.4.0", 1.0, "TEST ROOT CA"
                )

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
        with mock.patch.object(module.ssl, "create_default_context", return_value=object()), mock.patch.object(
            module, "_get_json", side_effect=responses
        ), mock.patch.object(module.time, "sleep", return_value=None), mock.patch.object(
            module.time, "monotonic", side_effect=[0.0, 0.0, 2.0]
        ):
            with self.assertRaises(RuntimeError):
                module.wait_for_readiness(
                    "https://93.184.216.34:40443", "0.4.0", 1.0, "TEST ROOT CA"
                )


if __name__ == "__main__":
    unittest.main()
