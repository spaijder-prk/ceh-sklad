from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


_CERT_SHA256_RE = re.compile(
    r"Signer #\d+ certificate SHA-256 digest:\s*([0-9A-Fa-f:]{64,95})"
)


def validate_api_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Android release API URL должен быть полноценным HTTPS origin")
    if parsed.username or parsed.password:
        raise ValueError("Учетные данные запрещено помещать в Android release API URL")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Android release API URL не должен содержать path/query/fragment")
    return normalized + "/"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_signer_sha256(output: str) -> str:
    match = _CERT_SHA256_RE.search(output)
    if not match:
        raise ValueError("apksigner не вернул SHA-256 сертификата подписи")
    digest = match.group(1).replace(":", "").lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("Некорректный SHA-256 сертификата подписи")
    return digest


def read_apk_metadata(metadata_path: Path, apk_path: Path) -> dict[str, Any]:
    raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("output-metadata.json должен быть JSON-объектом")
    application_id = str(raw.get("applicationId") or "")
    elements = raw.get("elements")
    if not application_id or not isinstance(elements, list):
        raise ValueError("output-metadata.json не содержит applicationId/elements")

    candidates = [item for item in elements if isinstance(item, dict)]
    selected = next(
        (item for item in candidates if str(item.get("outputFile") or "") == apk_path.name),
        None,
    )
    if selected is None:
        if len(candidates) != 1:
            raise ValueError("Не удалось однозначно сопоставить APK с output-metadata.json")
        selected = candidates[0]

    version_code = selected.get("versionCode")
    version_name = selected.get("versionName")
    if not isinstance(version_code, int) or version_code <= 0:
        raise ValueError("Некорректный versionCode в output-metadata.json")
    if not isinstance(version_name, str) or not version_name.strip():
        raise ValueError("Некорректный versionName в output-metadata.json")

    return {
        "application_id": application_id,
        "version_code": version_code,
        "version_name": version_name.strip(),
    }


def build_manifest(
    apk_path: Path,
    metadata_path: Path,
    *,
    api_base_url: str,
    signer_output: str,
    source_commit: str | None = None,
) -> dict[str, Any]:
    if not apk_path.is_file() or apk_path.stat().st_size <= 0:
        raise ValueError("Release APK отсутствует или пуст")
    if not metadata_path.is_file():
        raise ValueError("Не найден output-metadata.json release APK")

    metadata = read_apk_metadata(metadata_path, apk_path)
    if metadata["application_id"] != "ru.ceh.sklad":
        raise ValueError(
            f"Неожиданный applicationId: {metadata['application_id']!r}; ожидался 'ru.ceh.sklad'"
        )

    return {
        "schema_version": 1,
        "artifact": apk_path.name,
        "artifact_size_bytes": apk_path.stat().st_size,
        "artifact_sha256": sha256_file(apk_path),
        "signer_certificate_sha256": parse_signer_sha256(signer_output),
        "application_id": metadata["application_id"],
        "version_code": metadata["version_code"],
        "version_name": metadata["version_name"],
        "api_base_url": validate_api_base_url(api_base_url),
        "source_commit": source_commit or None,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сформировать безопасный manifest подписанного Android release APK"
    )
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--apksigner", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = subprocess.run(
        [str(args.apksigner), "verify", "--print-certs", str(args.apk)],
        check=True,
        capture_output=True,
        text=True,
    )
    manifest = build_manifest(
        args.apk,
        args.metadata,
        api_base_url=args.api_base_url,
        signer_output=result.stdout + "\n" + result.stderr,
        source_commit=os.getenv("GITHUB_SHA"),
    )
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
