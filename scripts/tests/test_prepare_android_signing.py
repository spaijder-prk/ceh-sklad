from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import prepare_android_signing as signing  # noqa: E402


class PrepareAndroidSigningTests(unittest.TestCase):
    @staticmethod
    def _keytool_runner(args, **kwargs):
        keystore = Path(args[args.index("-keystore") + 1])
        keystore.write_bytes(b"fake-pkcs12-keystore")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    def test_validation(self) -> None:
        self.assertEqual(signing.validate_alias("ceh-sklad-release"), "ceh-sklad-release")
        self.assertEqual(signing.validate_repository("spaijder-prk/ceh-sklad"), "spaijder-prk/ceh-sklad")

        for value in ("", "bad alias", "алиас"):
            with self.subTest(alias=value), self.assertRaises(ValueError):
                signing.validate_alias(value)

        for value in ("repo", "/repo", "owner/", "owner/repo/extra"):
            with self.subTest(repository=value), self.assertRaises(ValueError):
                signing.validate_repository(value)

    def test_prepare_creates_private_backup_and_uploads_expected_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "signing"
            uploaded: dict[str, str] = {}

            def set_secret(name: str, value: str, repository: str) -> None:
                self.assertEqual(repository, "spaijder-prk/ceh-sklad")
                uploaded[name] = value

            result = signing.prepare_signing(
                output_dir=output,
                alias="ceh-sklad-release",
                dname="CN=Цех Склад",
                validity_days=10000,
                keytool_path="/usr/bin/keytool",
                repository="spaijder-prk/ceh-sklad",
                secret_setter=set_secret,
                runner=self._keytool_runner,
            )

            keystore = output / "ceh-sklad-release.p12"
            backup_path = output / "ceh-sklad-signing-backup.json"
            backup = json.loads(backup_path.read_text(encoding="utf-8"))

            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(keystore.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(backup_path.stat().st_mode), 0o600)
            self.assertEqual(result["status"], "prepared")
            self.assertTrue(result["github_secrets_uploaded"])
            self.assertNotIn("keystore_password", result)
            self.assertNotIn("key_password", result)

            expected_names = {
                signing.SECRET_KEYSTORE,
                signing.SECRET_STORE_PASSWORD,
                signing.SECRET_ALIAS,
                signing.SECRET_KEY_PASSWORD,
            }
            self.assertEqual(set(uploaded), expected_names)
            self.assertEqual(uploaded[signing.SECRET_ALIAS], "ceh-sklad-release")
            self.assertEqual(
                uploaded[signing.SECRET_STORE_PASSWORD],
                uploaded[signing.SECRET_KEY_PASSWORD],
            )
            self.assertEqual(
                backup["keystore_password"],
                uploaded[signing.SECRET_STORE_PASSWORD],
            )
            self.assertEqual(backup["key_alias"], uploaded[signing.SECRET_ALIAS])
            self.assertEqual(backup["keystore_sha256"], signing.sha256_file(keystore))

    def test_existing_signing_material_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "signing"
            signing.prepare_signing(
                output_dir=output,
                alias="ceh-sklad-release",
                dname="CN=Цех Склад",
                validity_days=10000,
                keytool_path="/usr/bin/keytool",
                runner=self._keytool_runner,
            )

            with self.assertRaises(FileExistsError):
                signing.prepare_signing(
                    output_dir=output,
                    alias="ceh-sklad-release",
                    dname="CN=Цех Склад",
                    validity_days=10000,
                    keytool_path="/usr/bin/keytool",
                    runner=self._keytool_runner,
                )

    def test_repository_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            root.mkdir()
            (root / ".git").mkdir()
            output = root / "private-signing"

            with self.assertRaisesRegex(ValueError, "Git-репозитория"):
                signing.ensure_outside_repository(output, cwd=root)


if __name__ == "__main__":
    unittest.main()
