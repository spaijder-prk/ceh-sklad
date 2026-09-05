#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import quote

DOMAIN_RE = re.compile(
    r"^(?=.{4,253}$)(?!-)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOGIN_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
FORBIDDEN_DOMAINS = {"localhost", "example.com", "example.ru", "ci.invalid"}


def fail(message: str):
    raise SystemExit(message)


def normalize_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    if "://" in domain or "/" in domain or ":" in domain:
        fail("CEH_DOMAIN должен быть только DNS-именем без схемы, пути и порта")
    if domain in FORBIDDEN_DOMAINS or domain.endswith((".invalid", ".localhost", ".example")):
        fail("CEH_DOMAIN не должен быть тестовым или localhost-доменом")
    if not DOMAIN_RE.fullmatch(domain):
        fail("Некорректный CEH_DOMAIN: требуется полноценное DNS-имя")
    return domain


def validate_email(value: str) -> str:
    email = value.strip()
    if not EMAIL_RE.fullmatch(email):
        fail("Некорректный ACME email")
    return email


def validate_login(value: str) -> str:
    login = value.strip()
    if not LOGIN_RE.fullmatch(login):
        fail("Логин администратора: 3-64 символа A-Z, a-z, 0-9, '.', '_' или '-'")
    return login


def random_secret(size: int = 48) -> str:
    return secrets.token_urlsafe(size)


def build_env(domain: str, email: str, admin_login: str) -> str:
    db_password = random_secret(32)
    jwt_secret = random_secret(48)
    integration_key = random_secret(48)
    admin_password = random_secret(24)
    database_url = (
        "postgresql+asyncpg://ceh:"
        f"{quote(db_password, safe='')}@db:5432/ceh_sklad"
    )
    lines = [
        f"CEH_DOMAIN={domain}",
        f"ACME_EMAIL={email}",
        "APP_NAME=Цех Склад",
        "POSTGRES_DB=ceh_sklad",
        "POSTGRES_USER=ceh",
        f"POSTGRES_PASSWORD={db_password}",
        f"DATABASE_URL={database_url}",
        f"JWT_SECRET={jwt_secret}",
        "ACCESS_TOKEN_MINUTES=720",
        f"BOOTSTRAP_ADMIN_LOGIN={admin_login}",
        f"BOOTSTRAP_ADMIN_PASSWORD={admin_password}",
        f"INTEGRATION_1C_API_KEY={integration_key}",
        "",
    ]
    return "\n".join(lines)


def secure_write(path: Path, content: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Безопасно создать .env.production для первого запуска Цех Склад"
    )
    parser.add_argument("--domain", required=True, help="Рабочий DNS-домен без https://")
    parser.add_argument("--email", required=True, help="Email для ACME/Let's Encrypt")
    parser.add_argument("--admin-login", default="admin", help="Логин первого администратора")
    parser.add_argument(
        "--output",
        default=".env.production",
        help="Файл назначения; существующий файл никогда не перезаписывается",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    domain = normalize_domain(args.domain)
    email = validate_email(args.email)
    admin_login = validate_login(args.admin_login)
    output = Path(args.output).expanduser()

    if output.exists():
        fail(f"{output} уже существует; удалите/переименуйте его вручную, если нужен новый файл")
    if not output.parent.exists():
        fail(f"Каталог назначения не существует: {output.parent}")

    secure_write(output, build_env(domain, email, admin_login))

    print(f"Создан {output} с правами 0600.")
    print("Секреты сгенерированы локально и не выводились в консоль.")
    print(f"Проверьте: docker compose --env-file {output} -f docker-compose.production.yml config")
    print(
        "Перед запуском сохраните BOOTSTRAP_ADMIN_PASSWORD из файла в менеджер паролей; "
        "после первого входа смените его."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
