from __future__ import annotations

import importlib.util
import re
import stat
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_DIR.parent
SCRIPT_PATH = SCRIPTS_DIR / "prepare_production_env.py"
COMPOSE_PATH = REPO_ROOT / "docker-compose.production.yml"

spec = importlib.util.spec_from_file_location("prepare_production_env", SCRIPT_PATH)
assert spec and spec.loader
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def parse_env(content: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in content.splitlines() if line and not line.startswith("#"))


class PrepareProductionEnvTests(unittest.TestCase):
    def test_domain_normalization(self) -> None:
        self.assertEqual(prepare.normalize_domain(" Sklad.Company.RU. "), "sklad.company.ru")

        for value in (
            "localhost",
            "https://sklad.company.ru",
            "sklad.company.ru/path",
            "sklad.company.ru:443",
            "ci.invalid",
            "sklad.example",
            "no-dot",
            "-bad.company.ru",
        ):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                prepare.normalize_domain(value)

    def test_email_and_login_validation(self) -> None:
        self.assertEqual(prepare.validate_email(" ops@company.ru "), "ops@company.ru")
        self.assertEqual(prepare.validate_login("admin.prod"), "admin.prod")

        for value in ("invalid", "@company.ru", "ops @company.ru"):
            with self.subTest(email=value), self.assertRaises(SystemExit):
                prepare.validate_email(value)

        for value in ("ab", "админ", "admin prod", "x" * 65):
            with self.subTest(login=value), self.assertRaises(SystemExit):
                prepare.validate_login(value)

    def test_generated_env_matches_compose_contract(self) -> None:
        content = prepare.build_env("sklad.company.ru", "ops@company.ru", "admin.prod")
        env = parse_env(content)

        compose = COMPOSE_PATH.read_text(encoding="utf-8")
        referenced = set(re.findall(r"\$\{([A-Z0-9_]+)(?::[-?][^}]*)?\}", compose))
        missing = referenced - set(env)
        self.assertFalse(missing, f"Генератор не создаёт переменные Compose: {sorted(missing)}")

        self.assertEqual(env["CEH_DOMAIN"], "sklad.company.ru")
        self.assertEqual(env["ACME_EMAIL"], "ops@company.ru")
        self.assertEqual(env["BOOTSTRAP_ADMIN_LOGIN"], "admin.prod")
        self.assertEqual(env["POSTGRES_USER"], "ceh")
        self.assertEqual(env["POSTGRES_DB"], "ceh_sklad")

        parsed_url = urlsplit(env["DATABASE_URL"])
        self.assertEqual(parsed_url.scheme, "postgresql+asyncpg")
        self.assertEqual(parsed_url.hostname, "db")
        self.assertEqual(parsed_url.port, 5432)
        self.assertEqual(parsed_url.username, "ceh")
        self.assertEqual(unquote(parsed_url.password or ""), env["POSTGRES_PASSWORD"])
        self.assertEqual(parsed_url.path, "/ceh_sklad")

        secret_names = (
            "POSTGRES_PASSWORD",
            "JWT_SECRET",
            "BOOTSTRAP_ADMIN_PASSWORD",
            "INTEGRATION_1C_API_KEY",
        )
        secrets = [env[name] for name in secret_names]
        self.assertEqual(len(secrets), len(set(secrets)))
        self.assertGreaterEqual(len(env["JWT_SECRET"]), 32)
        self.assertGreaterEqual(len(env["BOOTSTRAP_ADMIN_PASSWORD"]), 12)
        self.assertGreaterEqual(len(env["INTEGRATION_1C_API_KEY"]), 32)
        self.assertNotIn("замените", content.lower())
        self.assertNotIn("change-me", content.lower())

    def test_secure_write_is_private_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / ".env.production"
            prepare.secure_write(target, "SECRET=value\n")

            self.assertEqual(target.read_text(encoding="utf-8"), "SECRET=value\n")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

            with self.assertRaises(FileExistsError):
                prepare.secure_write(target, "SECRET=other\n")

            self.assertEqual(target.read_text(encoding="utf-8"), "SECRET=value\n")


if __name__ == "__main__":
    unittest.main()
