from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.android_release_manifest import (  # noqa: E402
    build_manifest,
    parse_signer_sha256,
    validate_api_base_url,
)


def test_android_release_manifest_contains_hash_signer_version_and_url(tmp_path: Path):
    apk = tmp_path / "app-release.apk"
    apk.write_bytes(b"signed-apk-test")
    metadata = tmp_path / "output-metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "applicationId": "ru.ceh.sklad",
                "elements": [
                    {
                        "versionCode": 1,
                        "versionName": "0.4.0",
                        "outputFile": "app-release.apk",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    signer_digest = "ab" * 32

    manifest = build_manifest(
        apk,
        metadata,
        api_base_url="https://sklad.example.ru/",
        signer_output=f"Signer #1 certificate SHA-256 digest: {signer_digest}\n",
        source_commit="deadbeef",
    )

    assert manifest["artifact_sha256"] == hashlib.sha256(b"signed-apk-test").hexdigest()
    assert manifest["signer_certificate_sha256"] == signer_digest
    assert manifest["application_id"] == "ru.ceh.sklad"
    assert manifest["version_code"] == 1
    assert manifest["version_name"] == "0.4.0"
    assert manifest["api_base_url"] == "https://sklad.example.ru/"
    assert manifest["source_commit"] == "deadbeef"


def test_parse_signer_sha256_accepts_colon_separated_digest():
    digest = ":".join(["AB"] * 32)
    assert parse_signer_sha256(
        f"Signer #1 certificate SHA-256 digest: {digest}"
    ) == "ab" * 32


@pytest.mark.parametrize(
    "url",
    [
        "http://sklad.example.ru/",
        "https://user:password@sklad.example.ru/",
        "https://sklad.example.ru/api/v1",
        "https://sklad.example.ru/?token=x",
    ],
)
def test_android_release_manifest_rejects_unsafe_api_url(url: str):
    with pytest.raises(ValueError):
        validate_api_base_url(url)


def test_android_release_manifest_rejects_unexpected_application_id(tmp_path: Path):
    apk = tmp_path / "app-release.apk"
    apk.write_bytes(b"apk")
    metadata = tmp_path / "output-metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "applicationId": "ru.example.wrong",
                "elements": [
                    {
                        "versionCode": 1,
                        "versionName": "1.0",
                        "outputFile": "app-release.apk",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="applicationId"):
        build_manifest(
            apk,
            metadata,
            api_base_url="https://sklad.example.ru/",
            signer_output=f"Signer #1 certificate SHA-256 digest: {'cd' * 32}",
        )
