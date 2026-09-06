#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import os
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import quote

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOGIN_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


def fail(message: str):
    raise SystemExit(message)


def normalize_public_ip(value: str) -> str:
    raw = value.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    try:
        address = ipaddress.ip_address(raw)
    except ValueError as exc:
        fail(f"Некорректный CEH_PUBLIC_IP: {exc}")
    if not address.is_global:
        fail("CEH_PUBLIC_IP должен быть публичным глобально маршрутизируемым IPv4/IPv6 адресом")
    return address.compressed


def normalize_port(value: int | str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        fail("CEH_PUBLIC_PORT должен быть целым числом")
    if port < 1 or port > 65535:
        fail("CEH_PUBLIC_PORT должен быть в диапазоне 1..65535")
    if port == 80:
        fail("CEH_PUBLIC_PORT=80 запрещён: TCP 80 зарезервирован для ACME HTTP-01")
    return port


def public_host(ip: str) -> str:
    address = ipaddress.ip_address(ip)
    return f"[{address.compressed}]" if address.version == 6 else address.compressed


def public_origins(ip: str, port: int) -> tuple[str, str]:
    host = public_host(ip)
    suffix = "" if port == 443 else f":{port}"
    return f"https://{host}{suffix}", f"wss://{host}{suffix}"


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


def build_env(ip: str, port: int, email: str, admin_login: str) -> str:
    normalized_ip = normalize_public_ip(ip)
    normalized_port = normalize_port(port)
    host = public_host(normalized_ip)
    origin, ws_origin = public_origins(normalized_ip, normalized_port)
    db_password = random_secret(32)
    jwt_secret = random_secret(48)
    integration_key = random_secret(48)
    admin_password = random_secret(24)
    database_url = (
        "postgresql+asyncpg://ceh:"
        f"{quote(db_password, safe='')}@db:5432/ceh_sklad"
    )
    lines = [
        f"CEH_PUBLIC_IP={normalized_ip}",
        f"CEH_PUBLIC_HOST={host}",
        f"CEH_PUBLIC_PORT={normalized_port}",
        f"CEH_PUBLIC_ORIGIN={origin}",
        f"CEH_PUBLIC_WS_ORIGIN={ws_origin}",
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
        description="Безопасно создать .env.production для первого запуска Цех Склад по публичному IP"
    )
    parser.add_argument("--ip", required=True, help="Публичный IPv4/IPv6 адрес production host")
    parser.add_argument("--port", required=True, type=int, help="Внешний HTTPS-порт приложения")
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
    ip = normalize_public_ip(args.ip)
    port = normalize_port(args.port)
    email = validate_email(args.email)
    admin_login = validate_login(args.admin_login)
    output = Path(args.output).expanduser()

    if output.exists():
        fail(f"{output} уже существует; удалите/переименуйте его вручную, если нужен новый файл")
    if not output.parent.exists():
        fail(f"Каталог назначения не существует: {output.parent}")

    secure_write(output, build_env(ip, port, email, admin_login))

    origin, _ = public_origins(ip, port)
    print(f"Создан {output} с правами 0600.")
    print("Секреты сгенерированы локально и не выводились в консоль.")
    print(f"Production origin: {origin}")
    print("Для публично доверенного IP-сертификата TCP 80 должен доходить до Caddy для ACME HTTP-01.")
    print(f"Проверьте: docker compose --env-file {output} -f docker-compose.production.yml config")
    print(
        "Перед запуском сохраните BOOTSTRAP_ADMIN_PASSWORD из файла в менеджер паролей; "
        "после первого входа смените пароль администратора."
    )
    print(
        "После подтверждения нового пароля удалите из .env.production обе строки "
        "BOOTSTRAP_ADMIN_LOGIN/BOOTSTRAP_ADMIN_PASSWORD и повторно примените Compose: "
        "bootstrap больше не нужен и будет отключен."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
