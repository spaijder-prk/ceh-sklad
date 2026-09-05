from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from android_release_manifest import parse_signer_sha256, sha256_file, validate_api_base_url

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("Не найден android-release-manifest.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Android release manifest должен быть JSON-объектом")
    if raw.get("schema_version") != 1:
        raise ValueError("Неподдерживаемая версия Android release manifest")
    if raw.get("application_id") != "ru.ceh.sklad":
        raise ValueError("Неожиданный application_id Android release")
    if not isinstance(raw.get("version_code"), int) or raw["version_code"] <= 0:
        raise ValueError("Некорректный version_code Android release")
    version_name = raw.get("version_name")
    if not isinstance(version_name, str) or not version_name.strip():
        raise ValueError("Некорректный version_name Android release")
    artifact_sha256 = str(raw.get("artifact_sha256") or "").lower()
    signer_sha256 = str(raw.get("signer_certificate_sha256") or "").lower()
    if not _SHA256_RE.fullmatch(artifact_sha256):
        raise ValueError("Некорректный artifact_sha256 в Android release manifest")
    if not _SHA256_RE.fullmatch(signer_sha256):
        raise ValueError("Некорректный signer_certificate_sha256 в Android release manifest")
    if not isinstance(raw.get("artifact_size_bytes"), int) or raw["artifact_size_bytes"] <= 0:
        raise ValueError("Некорректный artifact_size_bytes в Android release manifest")
    validate_api_base_url(str(raw.get("api_base_url") or ""))
    source_commit = raw.get("source_commit")
    if source_commit is not None and not _COMMIT_RE.fullmatch(str(source_commit)):
        raise ValueError("Некорректный source_commit в Android release manifest")
    return raw


def load_checksums(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError("Не найден SHA256SUMS.txt")
    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"Некорректная строка SHA256SUMS.txt: {line_number}")
        digest, filename = parts
        filename = filename.lstrip("*")
        digest = digest.lower()
        if not _SHA256_RE.fullmatch(digest):
            raise ValueError(f"Некорректный SHA-256 в строке {line_number}")
        if not filename or Path(filename).name != filename:
            raise ValueError(f"Некорректное имя файла в строке {line_number}")
        if filename in result:
            raise ValueError(f"Дублирующееся имя файла в SHA256SUMS.txt: {filename}")
        result[filename] = digest
    if not result:
        raise ValueError("SHA256SUMS.txt пуст")
    return result


def _require_file(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"{label} отсутствует или пуст")


def verify_release(
    *,
    apk: Path,
    aab: Path,
    manifest_path: Path,
    checksums_path: Path,
    apksigner: Path,
    jarsigner: str = "jarsigner",
    expected_api_base_url: str | None = None,
    expected_source_commit: str | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    _require_file(apk, "Release APK")
    _require_file(aab, "Release AAB")
    _require_file(apksigner, "apksigner")

    manifest = load_manifest(manifest_path)
    checksums = load_checksums(checksums_path)

    actual_apk_sha = sha256_file(apk)
    actual_aab_sha = sha256_file(aab)
    actual_manifest_sha = sha256_file(manifest_path)

    if actual_apk_sha != manifest["artifact_sha256"]:
        raise ValueError("SHA-256 APK не совпадает с android-release-manifest.json")
    if apk.stat().st_size != manifest["artifact_size_bytes"]:
        raise ValueError("Размер APK не совпадает с android-release-manifest.json")

    expected_files = {
        apk.name: actual_apk_sha,
        aab.name: actual_aab_sha,
        manifest_path.name: actual_manifest_sha,
    }
    for filename, digest in expected_files.items():
        if checksums.get(filename) != digest:
            raise ValueError(f"SHA256SUMS.txt не подтверждает файл {filename}")

    unexpected = set(checksums) - set(expected_files)
    if unexpected:
        raise ValueError(f"SHA256SUMS.txt содержит неожиданные файлы: {sorted(unexpected)}")

    apk_result = command_runner(
        [str(apksigner), "verify", "--verbose", "--print-certs", str(apk)],
        check=True,
        capture_output=True,
        text=True,
    )
    signer_sha256 = parse_signer_sha256(apk_result.stdout + "\n" + apk_result.stderr)
    if signer_sha256 != manifest["signer_certificate_sha256"]:
        raise ValueError("SHA-256 сертификата APK не совпадает с android-release-manifest.json")

    command_runner(
        [jarsigner, "-verify", str(aab)],
        check=True,
        capture_output=True,
        text=True,
    )

    if expected_api_base_url is not None:
        normalized_expected_url = validate_api_base_url(expected_api_base_url)
        if manifest["api_base_url"] != normalized_expected_url:
            raise ValueError("API URL в manifest не совпадает с ожидаемым production URL")

    if expected_source_commit is not None:
        if not _COMMIT_RE.fullmatch(expected_source_commit):
            raise ValueError("Некорректный ожидаемый source commit")
        if manifest.get("source_commit") != expected_source_commit:
            raise ValueError("source_commit в manifest не совпадает с ожидаемым commit")

    return {
        "status": "verified",
        "application_id": manifest["application_id"],
        "version_code": manifest["version_code"],
        "version_name": manifest["version_name"],
        "api_base_url": manifest["api_base_url"],
        "source_commit": manifest.get("source_commit"),
        "apk_sha256": actual_apk_sha,
        "aab_sha256": actual_aab_sha,
        "signer_certificate_sha256": signer_sha256,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Независимо проверить подготовленный Android release Цех Склад"
    )
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--aab", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--checksums", required=True, type=Path)
    parser.add_argument("--apksigner", required=True, type=Path)
    parser.add_argument("--jarsigner", default="jarsigner")
    parser.add_argument("--expected-api-base-url")
    parser.add_argument("--expected-source-commit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = verify_release(
        apk=args.apk,
        aab=args.aab,
        manifest_path=args.manifest,
        checksums_path=args.checksums,
        apksigner=args.apksigner,
        jarsigner=args.jarsigner,
        expected_api_base_url=args.expected_api_base_url,
        expected_source_commit=args.expected_source_commit,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
