#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import ssl
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def compose_command(*args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        ".env.production",
        "-f",
        "docker-compose.production.yml",
        *args,
    ]


def read_root_ca() -> str:
    result = subprocess.run(
        compose_command(
            "exec",
            "-T",
            "caddy",
            "cat",
            "/data/caddy/pki/authorities/local/root.crt",
        ),
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    pem = result.stdout.strip()
    if "BEGIN CERTIFICATE" not in pem:
        raise RuntimeError("Caddy root CA не найден. Сначала запустите production-контур.")
    return pem + "\n"


def fingerprint_sha256(pem: str) -> str:
    der = ssl.PEM_cert_to_DER_cert(pem)
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[index:index + 2] for index in range(0, len(digest), 2))


def write_public_cert(path: Path, pem: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        os.chmod(path.parent, 0o700)
    if path.exists():
        raise RuntimeError(f"{path} уже существует; не перезаписываю root CA автоматически")
    path.write_text(pem, encoding="ascii", newline="\n")
    if os.name == "posix":
        os.chmod(path, 0o644)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Экспортировать публичный root CA Caddy для доверенных клиентских устройств"
    )
    parser.add_argument(
        "--output",
        default="~/.ceh-sklad/tls/ceh-sklad-root-ca.crt",
        help="Куда сохранить публичный root-сертификат",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = Path(args.output).expanduser().resolve()
    try:
        pem = read_root_ca()
        write_public_cert(target, pem)
        print(f"Root CA сохранён: {target}")
        print(f"SHA-256 fingerprint: {fingerprint_sha256(pem)}")
        print("Это публичный сертификат: его можно устанавливать на доверенные компьютеры и Android-устройства.")
        print("Приватный ключ CA не экспортировался и остаётся в постоянном caddy_data volume.")
        return 0
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        print(f"Ошибка экспорта root CA: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
