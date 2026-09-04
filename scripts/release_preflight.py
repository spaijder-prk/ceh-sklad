from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class ReleasePreflightReport:
    status: str
    base_url: str
    backend_status: str | None
    database: str | None
    schema_revision: str | None
    expected_schema_revision: str | None
    integration_checked: bool
    contract_version: str | None
    target_configuration: str | None
    deployment: str | None
    outbox_items: int | None
    outbox_ready: int | None
    outbox_blocked: int | None
    blocking_samples: tuple[str, ...]
    checks: tuple[str, ...]
    errors: tuple[str, ...]


def validate_base_url(value: str) -> str:
    base_url = value.rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Release preflight разрешен только для полноценного HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("Учетные данные запрещено помещать в base URL")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("base URL должен содержать только HTTPS origin без path/query/fragment")
    return base_url


def _remote_error(stage: str, exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{stage}: HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.RequestError):
        return f"{stage}: {type(exc).__name__}: {exc}"
    return f"{stage}: {type(exc).__name__}: {exc}"


def _get_json(
    client: httpx.Client,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    response = client.get(path, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def run_preflight(
    base_url: str,
    *,
    integration_key: str | None = None,
    expected_schema_revision: str | None = None,
    require_unf_ready: bool = False,
    timeout: float = 15.0,
    transport: httpx.BaseTransport | None = None,
) -> ReleasePreflightReport:
    """Read-only release gate для внешнего ceh-sklad staging.

    Проверяет HTTPS readiness backend и, при наличии сервисного ключа, профиль/outbox
    УНФ. Никаких изменяющих HTTP-методов не выполняет.
    """

    base_url = validate_base_url(base_url)
    checks: list[str] = []
    errors: list[str] = []
    blocking_samples: list[str] = []

    backend_status: str | None = None
    database: str | None = None
    schema_revision: str | None = None
    integration_checked = False
    contract_version: str | None = None
    target_configuration: str | None = None
    deployment: str | None = None
    outbox_items: int | None = None
    outbox_ready: int | None = None
    outbox_blocked: int | None = None

    with httpx.Client(
        base_url=base_url,
        timeout=httpx.Timeout(timeout),
        follow_redirects=False,
        transport=transport,
        headers={"Accept": "application/json"},
    ) as client:
        try:
            ready_data = _get_json(client, "/health/ready")
            if not isinstance(ready_data, dict):
                raise RuntimeError("readiness вернул не JSON-объект")
            backend_status = str(ready_data.get("status")) if ready_data.get("status") is not None else None
            database = str(ready_data.get("database")) if ready_data.get("database") is not None else None
            schema_revision = (
                str(ready_data.get("schema_revision"))
                if ready_data.get("schema_revision") is not None
                else None
            )
            if backend_status != "ready" or database != "ok":
                errors.append(
                    f"backend readiness: status={backend_status!r}, database={database!r}"
                )
            elif not schema_revision:
                errors.append("backend readiness: отсутствует schema_revision")
            else:
                checks.append(f"backend ready; schema={schema_revision}")
            if expected_schema_revision and schema_revision != expected_schema_revision:
                errors.append(
                    "backend schema: "
                    f"ожидалась {expected_schema_revision}, получена {schema_revision or '—'}"
                )
            elif expected_schema_revision:
                checks.append(f"backend schema совпадает с {expected_schema_revision}")
        except Exception as exc:  # network/status/JSON должны попасть в отчет
            errors.append(_remote_error("backend readiness", exc))

        if integration_key:
            integration_checked = True
            integration_headers = {"X-1C-Key": integration_key}
            profile_ok = False
            try:
                profile = _get_json(
                    client,
                    "/api/v1/integration/1c/unf/profile",
                    headers=integration_headers,
                )
                if not isinstance(profile, dict):
                    raise RuntimeError("UNF profile вернул не JSON-объект")
                contract_version = (
                    str(profile.get("contract_version"))
                    if profile.get("contract_version") is not None
                    else None
                )
                target_configuration = (
                    str(profile.get("target_configuration"))
                    if profile.get("target_configuration") is not None
                    else None
                )
                deployment = (
                    str(profile.get("deployment"))
                    if profile.get("deployment") is not None
                    else None
                )
                if contract_version != "unf-cloud-v2":
                    errors.append(
                        f"UNF profile: ожидался unf-cloud-v2, получен {contract_version!r}"
                    )
                elif target_configuration != "1С:Управление нашей фирмой":
                    errors.append(
                        f"UNF profile: неожиданная конфигурация {target_configuration!r}"
                    )
                elif deployment != "cloud":
                    errors.append(f"UNF profile: deployment должен быть cloud, получен {deployment!r}")
                else:
                    profile_ok = True
                    checks.append("UNF integration profile unf-cloud-v2/cloud принят")
            except Exception as exc:
                errors.append(_remote_error("UNF profile", exc))

            if profile_ok:
                try:
                    rows = _get_json(
                        client,
                        "/api/v1/integration/1c/unf/outbox",
                        headers=integration_headers,
                        params={"limit": 100},
                    )
                    if not isinstance(rows, list):
                        raise RuntimeError("UNF outbox вернул не JSON-массив")
                    outbox_items = len(rows)
                    blocked_rows = [
                        row
                        for row in rows
                        if not isinstance(row, dict) or not bool(row.get("ready_for_unf", False))
                    ]
                    outbox_blocked = len(blocked_rows)
                    outbox_ready = outbox_items - outbox_blocked
                    checks.append(
                        f"UNF outbox: всего={outbox_items}, готовы={outbox_ready}, blocked={outbox_blocked}"
                    )
                    for row in blocked_rows[:5]:
                        if not isinstance(row, dict):
                            blocking_samples.append("неожиданный элемент outbox")
                            continue
                        kind = str(row.get("kind") or row.get("entity_type") or "unknown")
                        internal_id = str(row.get("internal_id") or "unknown")
                        reasons = "; ".join(str(value) for value in (row.get("blocking_reasons") or []))
                        blocking_samples.append(
                            f"{kind} {internal_id}: {reasons or 'ready_for_unf=false'}"
                        )
                    if require_unf_ready and outbox_blocked:
                        errors.append(
                            f"UNF outbox содержит {outbox_blocked} объектов без обязательных сопоставлений"
                        )
                except Exception as exc:
                    errors.append(_remote_error("UNF outbox", exc))
        elif require_unf_ready:
            errors.append(
                "Для --require-unf-ready требуется CEH_STAGING_1C_KEY или CEH_1C_KEY"
            )
        else:
            checks.append("UNF integration check пропущен: сервисный ключ не задан")

    return ReleasePreflightReport(
        status="ready" if not errors else "degraded",
        base_url=base_url,
        backend_status=backend_status,
        database=database,
        schema_revision=schema_revision,
        expected_schema_revision=expected_schema_revision,
        integration_checked=integration_checked,
        contract_version=contract_version,
        target_configuration=target_configuration,
        deployment=deployment,
        outbox_items=outbox_items,
        outbox_ready=outbox_ready,
        outbox_blocked=outbox_blocked,
        blocking_samples=tuple(blocking_samples),
        checks=tuple(checks),
        errors=tuple(errors),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only release preflight внешнего staging ceh-sklad"
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-schema-revision")
    parser.add_argument("--require-unf-ready", action="store_true")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", type=Path, help="Дополнительно сохранить JSON-отчет в файл")
    return parser.parse_args()


def _write_report(report: ReleasePreflightReport, output: Path | None) -> None:
    payload = json.dumps(asdict(report), ensure_ascii=False, sort_keys=True, indent=2)
    print(payload)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    integration_key = os.getenv("CEH_STAGING_1C_KEY") or os.getenv("CEH_1C_KEY")
    try:
        report = run_preflight(
            args.base_url,
            integration_key=integration_key,
            expected_schema_revision=args.expected_schema_revision,
            require_unf_ready=args.require_unf_ready,
            timeout=args.timeout,
        )
    except ValueError as exc:
        print(
            json.dumps(
                {"status": "invalid", "errors": [str(exc)]},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        sys.exit(2)

    _write_report(report, args.output)
    if report.status != "ready":
        sys.exit(3)


if __name__ == "__main__":
    main()
