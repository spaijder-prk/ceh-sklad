from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import verify_android_release as verifier  # noqa: E402


class VerifyAndroidReleaseTests(unittest.TestCase):
    def _prepare_release(self, root: Path, signer_sha: str = "ab" * 32) -> dict[str, Path | str]:
        apk = root / "ceh-sklad-0.4.0.apk"
        aab = root / "ceh-sklad-0.4.0.aab"
        manifest_path = root / "android-release-manifest.json"
        checksums = root / "SHA256SUMS.txt"
        apksigner = root / "apksigner"

        apk.write_bytes(b"apk-release-payload")
        aab.write_bytes(b"aab-release-payload")
        apksigner.write_text("#!/bin/sh\n", encoding="utf-8")

        source_commit = "1" * 40
        manifest = {
            "schema_version": 1,
            "artifact": "app-release.apk",
            "artifact_size_bytes": apk.stat().st_size,
            "artifact_sha256": verifier.sha256_file(apk),
            "signer_certificate_sha256": signer_sha,
            "application_id": "ru.ceh.sklad",
            "version_code": 1,
            "version_name": "0.4.0",
            "api_base_url": "https://sklad.company.ru/",
            "source_commit": source_commit,
            "generated_at_utc": "2026-09-05T00:00:00+00:00",
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        checksums.write_text(
            "\n".join(
                (
                    f"{verifier.sha256_file(apk)}  {apk.name}",
                    f"{verifier.sha256_file(aab)}  {aab.name}",
                    f"{verifier.sha256_file(manifest_path)}  {manifest_path.name}",
                    "",
                )
            ),
            encoding="utf-8",
        )
        return {
            "apk": apk,
            "aab": aab,
            "manifest": manifest_path,
            "checksums": checksums,
            "apksigner": apksigner,
            "source_commit": source_commit,
            "signer_sha": signer_sha,
        }

    @staticmethod
    def _runner(signer_sha: str):
        def run(args, **kwargs):
            if "--print-certs" in args:
                output = f"Signer #1 certificate SHA-256 digest: {signer_sha}\n"
            else:
                output = "jar verified\n"
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=output, stderr="")

        return run

    def test_valid_release_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data = self._prepare_release(Path(temp_dir))
            result = verifier.verify_release(
                apk=data["apk"],
                aab=data["aab"],
                manifest_path=data["manifest"],
                checksums_path=data["checksums"],
                apksigner=data["apksigner"],
                expected_api_base_url="https://sklad.company.ru",
                expected_source_commit=data["source_commit"],
                command_runner=self._runner(data["signer_sha"]),
            )

            self.assertEqual(result["status"], "verified")
            self.assertEqual(result["application_id"], "ru.ceh.sklad")
            self.assertEqual(result["version_name"], "0.4.0")
            self.assertEqual(result["source_commit"], data["source_commit"])

    def test_tampered_apk_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data = self._prepare_release(Path(temp_dir))
            data["apk"].write_bytes(b"tampered")

            with self.assertRaisesRegex(ValueError, "SHA-256 APK"):
                verifier.verify_release(
                    apk=data["apk"],
                    aab=data["aab"],
                    manifest_path=data["manifest"],
                    checksums_path=data["checksums"],
                    apksigner=data["apksigner"],
                    command_runner=self._runner(data["signer_sha"]),
                )

    def test_wrong_signer_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data = self._prepare_release(Path(temp_dir))

            with self.assertRaisesRegex(ValueError, "сертификата APK"):
                verifier.verify_release(
                    apk=data["apk"],
                    aab=data["aab"],
                    manifest_path=data["manifest"],
                    checksums_path=data["checksums"],
                    apksigner=data["apksigner"],
                    command_runner=self._runner("cd" * 32),
                )


if __name__ == "__main__":
    unittest.main()
