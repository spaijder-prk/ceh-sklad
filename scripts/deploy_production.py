#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import ssl
import stat
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError(f"{path}:{number}: ожидалась строка KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise RuntimeError(f"{path}:{number}: пустое имя переменной")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'\"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def validate_env_permissions(path: Path) -> None:
    if os.name != "posix":
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError(
            f"{path} доступен группе/остальным (mode {mode:04o}); выполните chmod 600 {path}"
        )


def validate_public_ip(value: str) -> str:
    raw = value.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    try:
        address = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise RuntimeError(f"CEH_PUBLIC_IP должен быть корректным IPv4/IPv6 адресом: {exc}") from exc
    if not address.is_global:
        raise RuntimeError("CEH_PUBLIC_IP должен быть публичным глобально маршрутизируемым адресом")
    return address.compressed


def validate_public_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise RuntimeError("CEH_PUBLIC_PORT должен быть целым числом") from exc
    if port < 1 or port > 65535:
        raise RuntimeError("CEH_PUBLIC_PORT должен быть в диапазоне 1..65535")
    return port


def public_host(ip: str) -> str:
    address = ipaddress.ip_address(ip)
    return f"[{address.compressed}]" if address.version == 6 else address.compressed


def public_origins(ip: str, port: int) -> tuple[str, str]:
    host = public_host(ip)
    suffix = "" if port == 443 else f":{port}"
    return f"https://{host}{suffix}", f"wss://{host}{suffix}"


def validate_public_endpoint(env_values: dict[str, str]) -> tuple[str, int, str]:
    ip = validate_public_ip(env_values.get("CEH_PUBLIC_IP", ""))
    port = validate_public_port(env_values.get("CEH_PUBLIC_PORT", ""))
    expected_host = public_host(ip)
    expected_origin, expected_ws_origin = public_origins(ip, port)

    if env_values.get("CEH_TLS_MODE") != "internal-ca":
        raise RuntimeError("CEH_TLS_MODE должен быть internal-ca для production без внешних 80/443")

    actual_host = env_values.get("CEH_PUBLIC_HOST", "")
    actual_origin = env_values.get("CEH_PUBLIC_ORIGIN", "").rstrip("/")
    actual_ws_origin = env_values.get("CEH_PUBLIC_WS_ORIGIN", "").rstrip("/")
    if actual_host != expected_host:
        raise RuntimeError(f"CEH_PUBLIC_HOST не совпадает с IP: {actual_host!r} != {expected_host!r}")
    if actual_origin != expected_origin:
        raise RuntimeError(
            f"CEH_PUBLIC_ORIGIN не совпадает с IP/портом: {actual_origin!r} != {expected_origin!r}"
        )
    if actual_ws_origin != expected_ws_origin:
        raise RuntimeError(
            "CEH_PUBLIC_WS_ORIGIN не совпадает с IP/портом: "
            f"{actual_ws_origin!r} != {expected_ws_origin!r}"
        )
    return ip, port, expected_origin


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


def run_command(
    command: list[str],
    *,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def running_services() -> set[str]:
    result = run_command(compose_command("ps", "--status", "running", "--services"), capture=True)
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def make_backup() -> None:
    run_command(["sh", "scripts/backup.sh", "--production"])


def read_caddy_root_ca(timeout: float = 45.0) -> str:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = run_command(
                compose_command(
                    "exec",
                    "-T",
                    "caddy",
                    "cat",
                    "/data/caddy/pki/authorities/local/root.crt",
                ),
                capture=True,
            )
            pem = result.stdout.strip()
            if "BEGIN CERTIFICATE" not in pem:
                raise RuntimeError("Caddy root CA ещё не создан")
            return pem + "\n"
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"Не удалось получить root CA Caddy: {last_error}")


def _get_json(url: str, timeout: float, context: ssl.SSLContext) -> dict[str, object]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "ceh-sklad-deploy/0.4"})
    with urlopen(request, timeout=timeout, context=context) as response:  # noqa: S310 - URL собран из проверенного public IP/port
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} вернул не JSON-объект")
    return payload


def wait_for_readiness(
    base_url: str,
    expected_version: str,
    timeout: float,
    root_ca_pem: str,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    base_url = base_url.rstrip("/")
    context = ssl.create_default_context(cadata=root_ca_pem)

    while time.monotonic() < deadline:
        try:
            live = _get_json(f"{base_url}/health", min(10.0, timeout), context)
            ready = _get_json(f"{base_url}/health/ready", min(10.0, timeout), context)
            if live.get("status") != "ok":
                raise RuntimeError(f"liveness status={live.get('status')!r}")
            if ready.get("status") != "ready" or ready.get("database") != "ok":
                raise RuntimeError(
                    f"readiness status={ready.get('status')!r}, database={ready.get('database')!r}"
                )
            live_version = str(live.get("version") or "")
            ready_version = str(ready.get("version") or "")
            if live_version != expected_version or ready_version != expected_version:
                raise RuntimeError(
                    "версия backend не совпала: "
                    f"health={live_version or '—'}, ready={ready_version or '—'}, expected={expected_version}"
                )
            if not ready.get("schema_revision"):
                raise RuntimeError("readiness не вернул schema_revision")
            return ready
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError, ssl.SSLError) as exc:
            last_error = exc
            time.sleep(3)

    raise RuntimeError(f"HTTPS readiness не стала готовой за {timeout:.0f} с: {last_error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Безопасно проверить или обновить production-контур Цех Склад по IP и нестандартному порту"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Только проверить env, endpoint, Docker daemon и Compose без backup/build/запуска",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Не создавать резервную копию уже работающей БД перед обновлением",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Не пересобирать backend/web images, использовать уже имеющиеся",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=240.0,
        help="Максимальное ожидание HTTPS readiness, секунд",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_path = REPO_ROOT / ".env.production"
    compose_path = REPO_ROOT / "docker-compose.production.yml"
    version_path = REPO_ROOT / "VERSION"

    if not env_path.is_file():
        raise SystemExit("Не найден .env.production. Сначала запустите scripts/prepare_production_env.py")
    if not compose_path.is_file():
        raise SystemExit("Не найден docker-compose.production.yml")
    if not version_path.is_file():
        raise SystemExit("Не найден VERSION")
    if args.timeout <= 0:
        raise SystemExit("--timeout должен быть больше нуля")

    try:
        validate_env_permissions(env_path)
        env_values = parse_env_file(env_path)
        ip, port, base_url = validate_public_endpoint(env_values)
        expected_version = version_path.read_text(encoding="utf-8").strip()
        if not expected_version:
            raise RuntimeError("VERSION пуст")

        print("1/6 Проверяю Docker daemon и Compose...")
        run_command(["docker", "info", "--format", "{{.ServerVersion}}"], capture=True)
        run_command(["docker", "compose", "version"])
        run_command(compose_command("config", "--quiet"))

        print("2/6 Проверяю production endpoint IP:port...")
        print(f"Endpoint: {base_url} (IP={ip}, HTTPS port={port}, TLS=internal-ca)")
        print("Внешние TCP 80/443 для сертификата не требуются; NAT должен пробрасывать только выбранный HTTPS-порт.")

        if args.check_only:
            print(
                "Preflight сервера успешен: env/права, public IP/port, internal-CA профиль, Docker daemon и Compose готовы. "
                "Контейнеры и данные не изменялись."
            )
            return 0

        services = running_services()
        if "db" in services and not args.skip_backup:
            print("3/6 БД уже работает: создаю резервную копию перед обновлением...")
            make_backup()
        elif "db" in services:
            print("3/6 БД уже работает: backup пропущен по --skip-backup.")
        else:
            print("3/6 Первый запуск: работающей БД нет, предварительный backup не требуется.")

        print("4/6 Поднимаю production-контур...")
        up_args = ["up", "-d"]
        if not args.no_build:
            up_args.append("--build")
        run_command(compose_command(*up_args))

        print("5/6 Получаю root CA Caddy и ожидаю внешний HTTPS health/readiness...")
        root_ca_pem = read_caddy_root_ca(min(45.0, args.timeout))
        ready = wait_for_readiness(base_url, expected_version, args.timeout, root_ca_pem)

        print("6/6 Проверяю состояние контейнеров...")
        run_command(compose_command("ps"))
        print(
            "Production готов: "
            f"{base_url}, version={expected_version}, schema={ready.get('schema_revision')}"
        )
        print(
            "Следующий шаг: экспортировать root CA командой scripts/export_internal_ca.py, "
            "установить его на доверенные компьютеры/Android, затем войти bootstrap-администратором."
        )
        return 0
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Ошибка production deployment: {exc}", file=sys.stderr)
        try:
            run_command(compose_command("ps"))
        except Exception:
            pass
        return 3


if __name__ == "__main__":
    sys.exit(main())
