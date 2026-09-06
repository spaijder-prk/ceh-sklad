#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import ssl
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ReleaseBackendReport:
    status: str
    base_url: str
    expected_version: str
    actual_version: str | None
    expected_schema_revision: str
    actual_schema_revision: str | None
    backend_status: str | None
    database: str | None
    errors: tuple[str, ...]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def validate_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("release backend должен быть полноценным HTTPS origin")
    if parsed.username or parsed.password:
        raise ValueError("credentials запрещены в release backend URL")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("release backend URL не должен содержать path/query/fragment")
    return base_url


def _assignment(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name and node.value is not None:
                return ast.literal_eval(node.value)
    raise ValueError(f"в migration отсутствует {name}")


def expected_version(repo_root: Path = REPO_ROOT) -> str:
    value = (repo_root / "VERSION").read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError("VERSION пуст")
    return value


def expected_schema_revision(repo_root: Path = REPO_ROOT) -> str:
    versions_dir = repo_root / "backend" / "alembic" / "versions"
    revisions: set[str] = set()
    referenced: set[str] = set()

    files = sorted(path for path in versions_dir.glob("*.py") if path.name != "__init__.py")
    if not files:
        raise ValueError("Alembic migrations не найдены")

    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        revision = _assignment(tree, "revision")
        down_revision = _assignment(tree, "down_revision")
        if not isinstance(revision, str) or not revision.strip():
            raise ValueError(f"некорректный revision в {path.name}")
        if revision in revisions:
            raise ValueError(f"дублирующий revision {revision}")
        revisions.add(revision)

        if down_revision is None:
            continue
        if isinstance(down_revision, str):
            referenced.add(down_revision)
        elif isinstance(down_revision, (tuple, list)) and all(isinstance(item, str) for item in down_revision):
            referenced.update(down_revision)
        else:
            raise ValueError(f"некорректный down_revision в {path.name}")

    unknown = referenced - revisions
    if unknown:
        raise ValueError(f"Alembic ссылается на отсутствующие revisions: {sorted(unknown)}")

    heads = sorted(revisions - referenced)
    if len(heads) != 1:
        raise ValueError(f"ожидался один Alembic head, найдено {heads}")
    return heads[0]


def verify_ready_payload(
    payload: Any,
    *,
    expected_version_value: str,
    expected_schema_revision_value: str,
) -> tuple[str | None, str | None, str | None, str | None, tuple[str, ...]]:
    if not isinstance(payload, dict):
        return None, None, None, None, ("/health/ready вернул не JSON-объект",)

    backend_status = str(payload.get("status")) if payload.get("status") is not None else None
    database = str(payload.get("database")) if payload.get("database") is not None else None
    actual_schema_revision = (
        str(payload.get("schema_revision")) if payload.get("schema_revision") is not None else None
    )
    actual_version = str(payload.get("version")) if payload.get("version") is not None else None

    errors: list[str] = []
    if backend_status != "ready":
        errors.append(f"backend status должен быть ready, получено {backend_status!r}")
    if database != "ok":
        errors.append(f"database должен быть ok, получено {database!r}")
    if actual_schema_revision != expected_schema_revision_value:
        errors.append(
            "schema_revision не совпадает: "
            f"ожидалась {expected_schema_revision_value}, получена {actual_schema_revision or '—'}"
        )
    if actual_version != expected_version_value:
        errors.append(
            f"backend version не совпадает: ожидалась {expected_version_value}, получена {actual_version or '—'}"
        )

    return backend_status, database, actual_schema_revision, actual_version, tuple(errors)


def build_ssl_context(ca_cert: Path | None) -> ssl.SSLContext:
    if ca_cert is None:
        return ssl.create_default_context()
    if not ca_cert.is_file():
        raise ValueError(f"CA certificate не найден: {ca_cert}")
    return ssl.create_default_context(cafile=str(ca_cert))


def fetch_ready(base_url: str, *, timeout: float = 15.0, ca_cert: Path | None = None) -> Any:
    context = build_ssl_context(ca_cert)
    opener = build_opener(_NoRedirect(), HTTPSHandler(context=context))
    request = Request(
        f"{base_url}/health/ready",
        headers={"Accept": "application/json", "User-Agent": "ceh-sklad-release-verifier/1"},
        method="GET",
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"/health/ready: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"/health/ready: {type(exc.reason).__name__}: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("/health/ready вернул некорректный JSON") from exc


def run_check(
    base_url: str,
    *,
    repo_root: Path = REPO_ROOT,
    timeout: float = 15.0,
    payload: Any | None = None,
    ca_cert: Path | None = None,
) -> ReleaseBackendReport:
    base_url = validate_base_url(base_url)
    version = expected_version(repo_root)
    schema_revision = expected_schema_revision(repo_root)
    errors: list[str] = []

    try:
        ready_payload = fetch_ready(base_url, timeout=timeout, ca_cert=ca_cert) if payload is None else payload
        backend_status, database, actual_schema_revision, actual_version, payload_errors = verify_ready_payload(
            ready_payload,
            expected_version_value=version,
            expected_schema_revision_value=schema_revision,
        )
        errors.extend(payload_errors)
    except Exception as exc:
        backend_status = None
        database = None
        actual_schema_revision = None
        actual_version = None
        errors.append(str(exc))

    return ReleaseBackendReport(
        status="ready" if not errors else "degraded",
        base_url=base_url,
        expected_version=version,
        actual_version=actual_version,
        expected_schema_revision=schema_revision,
        actual_schema_revision=actual_schema_revision,
        backend_status=backend_status,
        database=database,
        errors=tuple(errors),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only проверка production backend перед публикацией Android release"
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--ca-cert",
        type=Path,
        help="Дополнительный доверенный root CA PEM/CRT для production с внутренним CA",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = run_check(args.base_url, timeout=args.timeout, ca_cert=args.ca_cert)
    except (OSError, ValueError, SyntaxError) as exc:
        report = {
            "status": "invalid",
            "base_url": args.base_url,
            "errors": [str(exc)],
        }
        payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
        print(payload)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload + "\n", encoding="utf-8")
        return 2

    payload = json.dumps(asdict(report), ensure_ascii=False, sort_keys=True, indent=2)
    print(payload)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0 if report.status == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
