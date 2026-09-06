#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_RE = re.compile(
    r"^(?=.{4,253}$)(?!-)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


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


def validate_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    if not DOMAIN_RE.fullmatch(domain):
        raise RuntimeError("CEH_DOMAIN должен быть полноценным DNS-именем")
    if domain in {"localhost", "example.com", "example.ru"} or domain.endswith(
        (".invalid", ".localhost", ".example")
    ):
        raise RuntimeError("CEH_DOMAIN не должен быть тестовым или localhost-доменом")
    return domain


def resolve_domain(domain: str) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise RuntimeError(f"DNS для {domain} не разрешается: {exc}") from exc
    addresses = sorted({str(record[4][0]) for record in records if record[4]})
    if not addresses:
        raise RuntimeError(f"DNS для {domain} не вернул ни одного IP-адреса")
    return tuple(addresses)


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


def _get_json(url: str, timeout: float) -> dict[str, object]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "ceh-sklad-deploy/0.4"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL собран из проверенного CEH_DOMAIN
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} вернул не JSON-объект")
    return payload


def wait_for_readiness(domain: str, expected_version: str, timeout: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    base_url = f"https://{domain}"

    while time.monotonic() < deadline:
        try:
            live = _get_json(f"{base_url}/health", min(10.0, timeout))
            ready = _get_json(f"{base_url}/health/ready", min(10.0, timeout))
            if live.get("status") != "ok":
                raise RuntimeError(f"liveness status={live.get('status')!r}")
            if ready.get("status") != "ready" or ready.get("database") != "ok":
                raise RuntimeError(
                    f"readiness status={ready.get('status')!r}, database={database!r}"
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
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            last_error = exc
            time.sleep(3)

    raise RuntimeError(f"HTTPS readiness не стала готовой за {timeout:.0f} с: {last_error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Безопасно проверить или обновить production-контур Цех Склад"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Только проверить env, DNS, Docker daemon и Compose без backup/build/запуска",
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
        domain = validate_domain(env_values.get("CEH_DOMAIN", ""))
        expected_version = version_path.read_text(encoding="utf-8").strip()
        if not expected_version:
            raise RuntimeError("VERSION пуст")

        print("1/6 Проверяю Docker daemon и Compose...")
        run_command(["docker", "info", "--format", "{{.ServerVersion}}"], capture=True)
        run_command(["docker", "compose", "version"])
        run_command(compose_command("config", "--quiet"))

        print("2/6 Проверяю DNS рабочего домена...")
        addresses = resolve_domain(domain)
        print(f"DNS {domain}: {', '.join(addresses)}")

        if args.check_only:
            print(
                "Preflight сервера успешен: env/права, Docker daemon, Compose и DNS готовы. "
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

        print("5/6 Ожидаю внешний HTTPS health/readiness...")
        ready = wait_for_readiness(domain, expected_version, args.timeout)

        print("6/6 Проверяю состояние контейнеров...")
        run_command(compose_command("ps"))
        print(
            "Production готов: "
            f"https://{domain}, version={expected_version}, schema={ready.get('schema_revision')}"
        )
        print(
            "Следующий шаг: войти bootstrap-администратором, сменить пароль, подтвердить "
            "повторный вход, удалить обе BOOTSTRAP_ADMIN_* строки из .env.production и "
            "продолжить по docs/GO_LIVE.md."
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
