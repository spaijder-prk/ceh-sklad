from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

_ALIAS_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

SECRET_KEYSTORE = "CEH_ANDROID_KEYSTORE_BASE64"
SECRET_STORE_PASSWORD = "CEH_ANDROID_KEYSTORE_PASSWORD"
SECRET_ALIAS = "CEH_ANDROID_KEY_ALIAS"
SECRET_KEY_PASSWORD = "CEH_ANDROID_KEY_PASSWORD"


def fail(message: str) -> None:
    raise SystemExit(message)


def validate_alias(value: str) -> str:
    alias = value.strip()
    if not _ALIAS_RE.fullmatch(alias):
        raise ValueError("Alias должен содержать только A-Z, a-z, 0-9, '.', '_' или '-'")
    return alias


def validate_repository(value: str) -> str:
    repository = value.strip()
    if not _REPOSITORY_RE.fullmatch(repository):
        raise ValueError("Репозиторий должен иметь вид owner/name")
    return repository


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_private_directory(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"Путь существует и не является каталогом: {path}")
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise ValueError(
                f"Каталог {path} доступен группе/другим пользователям; требуется chmod 700"
            )
        return

    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)


def secure_write_json(path: Path, payload: dict[str, object]) -> None:
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def find_git_root(start: Path) -> Path | None:
    resolved = start.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def ensure_outside_repository(output_dir: Path, cwd: Path | None = None) -> None:
    root = find_git_root(cwd or Path.cwd())
    if root is None:
        return
    resolved_output = output_dir.expanduser().resolve()
    if resolved_output.is_relative_to(root.resolve()):
        raise ValueError(
            f"Signing key нельзя создавать внутри Git-репозитория: {resolved_output}"
        )


def _default_secret_setter(
    *,
    gh_path: str,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> Callable[[str, str, str], None]:
    def set_secret(name: str, value: str, repository: str) -> None:
        runner(
            [gh_path, "secret", "set", name, "--repo", repository],
            input=value,
            text=True,
            check=True,
            capture_output=True,
        )

    return set_secret


def prepare_signing(
    *,
    output_dir: Path,
    alias: str,
    dname: str,
    validity_days: int,
    keytool_path: str,
    repository: str | None = None,
    secret_setter: Callable[[str, str, str], None] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    alias = validate_alias(alias)
    if repository is not None:
        repository = validate_repository(repository)
    if validity_days < 9125:
        raise ValueError("Срок сертификата Android signing key должен быть не менее 9125 дней")
    if not dname.strip():
        raise ValueError("DN сертификата не должен быть пустым")
    if secret_setter is not None and repository is None:
        raise ValueError("Для загрузки GitHub Secrets требуется repository")

    output_dir = output_dir.expanduser()
    ensure_private_directory(output_dir)

    keystore_path = output_dir / "ceh-sklad-release.p12"
    backup_path = output_dir / "ceh-sklad-signing-backup.json"
    if keystore_path.exists() or backup_path.exists():
        raise FileExistsError(
            "Signing material уже существует; существующий production key никогда не перезаписывается"
        )

    password = secrets.token_urlsafe(36)
    env = os.environ.copy()
    env["CEH_GENERATED_KEYSTORE_PASSWORD"] = password

    command = [
        keytool_path,
        "-genkeypair",
        "-noprompt",
        "-keystore",
        str(keystore_path),
        "-storetype",
        "PKCS12",
        "-alias",
        alias,
        "-keyalg",
        "RSA",
        "-keysize",
        "4096",
        "-validity",
        str(validity_days),
        "-dname",
        dname.strip(),
        "-storepass:env",
        "CEH_GENERATED_KEYSTORE_PASSWORD",
        "-keypass:env",
        "CEH_GENERATED_KEYSTORE_PASSWORD",
    ]

    try:
        runner(
            command,
            check=True,
            env=env,
            capture_output=True,
            text=True,
        )
        if not keystore_path.is_file() or keystore_path.stat().st_size <= 0:
            raise ValueError("keytool не создал keystore")
        keystore_path.chmod(0o600)

        keystore_base64 = base64.b64encode(keystore_path.read_bytes()).decode("ascii")
        backup = {
            "schema_version": 1,
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "keystore_file": keystore_path.name,
            "keystore_sha256": sha256_file(keystore_path),
            "store_type": "PKCS12",
            "key_alias": alias,
            "keystore_password": password,
            "key_password": password,
            "certificate_dname": dname.strip(),
            "validity_days": validity_days,
            "github_repository": repository,
            "github_secret_names": [
                SECRET_KEYSTORE,
                SECRET_STORE_PASSWORD,
                SECRET_ALIAS,
                SECRET_KEY_PASSWORD,
            ],
        }
        secure_write_json(backup_path, backup)

        uploaded = False
        if secret_setter is not None and repository is not None:
            values = {
                SECRET_KEYSTORE: keystore_base64,
                SECRET_STORE_PASSWORD: password,
                SECRET_ALIAS: alias,
                SECRET_KEY_PASSWORD: password,
            }
            for name, value in values.items():
                secret_setter(name, value, repository)
            uploaded = True

        return {
            "status": "prepared",
            "keystore_path": str(keystore_path),
            "backup_path": str(backup_path),
            "keystore_sha256": backup["keystore_sha256"],
            "key_alias": alias,
            "github_repository": repository,
            "github_secrets_uploaded": uploaded,
        }
    except Exception:
        if not backup_path.exists():
            keystore_path.unlink(missing_ok=True)
        raise
    finally:
        env.pop("CEH_GENERATED_KEYSTORE_PASSWORD", None)
        password = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Создать production Android signing key и при необходимости загрузить GitHub Secrets"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("~/.ceh-sklad/android-signing"),
        help="Приватный каталог вне Git-репозитория",
    )
    parser.add_argument("--alias", default="ceh-sklad-release")
    parser.add_argument("--dname", default="CN=Цех Склад")
    parser.add_argument("--validity-days", type=int, default=10000)
    parser.add_argument("--repository", help="GitHub repository в формате owner/name")
    parser.add_argument(
        "--upload-secrets",
        action="store_true",
        help="Загрузить четыре CEH_ANDROID_* secret через авторизованный GitHub CLI",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser()
    ensure_outside_repository(output_dir)

    keytool_path = shutil.which("keytool")
    if not keytool_path:
        fail("Не найден keytool. Установите JDK 17+ и повторите команду.")

    secret_setter = None
    if args.upload_secrets:
        if not args.repository:
            fail("--upload-secrets требует --repository owner/name")
        gh_path = shutil.which("gh")
        if not gh_path:
            fail("Не найден GitHub CLI 'gh'. Установите его и выполните gh auth login.")
        secret_setter = _default_secret_setter(gh_path=gh_path, runner=subprocess.run)

    try:
        result = prepare_signing(
            output_dir=output_dir,
            alias=args.alias,
            dname=args.dname,
            validity_days=args.validity_days,
            keytool_path=keytool_path,
            repository=args.repository,
            secret_setter=secret_setter,
        )
    except (ValueError, FileExistsError, subprocess.CalledProcessError) as exc:
        fail(str(exc))

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    print(
        "Секретные значения не выводились. Сохраните keystore и backup JSON в защищенной "
        "офлайн-копии: без этого ключа обновление уже установленного приложения будет невозможно."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
