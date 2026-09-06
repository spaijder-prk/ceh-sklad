#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import ssl
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def _validated_https_origin(value: str, variable: str) -> str:
    configured = value.strip().rstrip("/")
    if not configured:
        raise ValueError(f"Не задан {variable}")
    parsed = urlsplit(configured)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{variable} должен быть полноценным HTTPS origin")
    if parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError(f"{variable} должен быть HTTPS origin без credentials/path/query/fragment")
    return configured


def _base_url() -> str:
    explicit = os.environ.get("CEH_MONITOR_BASE_URL", "")
    if explicit.strip():
        return _validated_https_origin(explicit, "CEH_MONITOR_BASE_URL")
    public_origin = os.environ.get("CEH_PUBLIC_ORIGIN", "")
    if public_origin.strip():
        return _validated_https_origin(public_origin, "CEH_PUBLIC_ORIGIN")
    raise ValueError("Не задан CEH_MONITOR_BASE_URL или CEH_PUBLIC_ORIGIN")


def _monitor_ssl_context() -> ssl.SSLContext:
    ca_value = os.environ.get("CEH_MONITOR_CA_CERT", "").strip()
    tls_mode = os.environ.get("CEH_TLS_MODE", "").strip()
    if not ca_value:
        if tls_mode == "internal-ca":
            raise ValueError("Для CEH_TLS_MODE=internal-ca задайте CEH_MONITOR_CA_CERT")
        return ssl.create_default_context()
    ca_path = Path(ca_value).expanduser()
    if not ca_path.is_file():
        raise ValueError(f"CEH_MONITOR_CA_CERT не найден: {ca_path}")
    return ssl.create_default_context(cafile=str(ca_path))


def _get_json(url: str, context: ssl.SSLContext) -> dict:
    request = Request(url, headers={"User-Agent": "ceh-sklad-production-monitor/1"})
    with urlopen(request, timeout=10, context=context) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Сервер вернул неожиданный JSON")
    return value


def _latest_backup(backup_dir: Path) -> Path:
    dumps = sorted(backup_dir.glob("ceh_sklad_*.dump"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not dumps:
        raise RuntimeError("production backup еще не найден")
    return dumps[0]


def _verify_checksum(dump: Path) -> None:
    sidecar = Path(f"{dump}.sha256")
    if not sidecar.is_file():
        raise RuntimeError(f"нет checksum для {dump.name}")
    expected = sidecar.read_text(encoding="utf-8").split()[0].lower()
    digest = hashlib.sha256()
    with dump.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest().lower() != expected:
        raise RuntimeError(f"checksum резервной копии {dump.name} не совпадает")


def _send_webhook(payload: dict) -> None:
    url = os.environ.get("CEH_MONITOR_WEBHOOK_URL", "").strip()
    if not url:
        return
    if not url.startswith("https://"):
        raise ValueError("CEH_MONITOR_WEBHOOK_URL должен использовать HTTPS")
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "ceh-sklad-production-monitor/1"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Webhook вернул HTTP {response.status}")


def main() -> int:
    errors: list[str] = []
    details: dict[str, object] = {}

    try:
        base_url = _base_url()
        context = _monitor_ssl_context()
        health = _get_json(f"{base_url}/health", context)
        ready = _get_json(f"{base_url}/health/ready", context)
        if health.get("status") != "ok":
            errors.append("/health не вернул status=ok")
        if ready.get("status") != "ready" or ready.get("database") != "ok":
            errors.append("/health/ready не подтвердил готовность PostgreSQL")
        details["base_url"] = base_url
        details["version"] = health.get("version")
        details["schema_revision"] = ready.get("schema_revision")
    except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError, json.JSONDecodeError, ssl.SSLError) as exc:
        errors.append(f"HTTPS health: {exc}")

    backup_dir = Path(os.environ.get("CEH_BACKUP_DIR", "backups"))
    max_age_hours = float(os.environ.get("CEH_BACKUP_MAX_AGE_HOURS", "30"))
    try:
        latest = _latest_backup(backup_dir)
        age_hours = (time.time() - latest.stat().st_mtime) / 3600
        _verify_checksum(latest)
        details["backup"] = latest.name
        details["backup_age_hours"] = round(age_hours, 2)
        if age_hours > max_age_hours:
            errors.append(f"последняя копия старше {max_age_hours:g} ч: {age_hours:.1f} ч")
    except (OSError, RuntimeError, ValueError) as exc:
        errors.append(f"backup: {exc}")

    min_free_percent = float(os.environ.get("CEH_DISK_MIN_FREE_PERCENT", "10"))
    try:
        usage = shutil.disk_usage(Path.cwd())
        free_percent = usage.free / usage.total * 100
        details["disk_free_percent"] = round(free_percent, 2)
        if free_percent < min_free_percent:
            errors.append(f"свободно только {free_percent:.1f}% диска")
    except OSError as exc:
        errors.append(f"disk: {exc}")

    payload = {
        "service": "ceh-sklad",
        "ok": not errors,
        "errors": errors,
        "details": details,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    if errors:
        try:
            _send_webhook(payload)
        except Exception as exc:  # webhook не должен скрывать исходную ошибку мониторинга
            print(f"Не удалось отправить webhook мониторинга: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
