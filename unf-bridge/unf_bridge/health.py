from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .ceh_client import CehSkladClient
from .models import UnfOutboxItem
from .odata import FreshODataClient, ODataEntitySet
from .planner import build_plan
from .tenant_audit import TenantAuditReport, audit_mapping_file
from .tenant_config import TenantMapping


@dataclass(frozen=True)
class BridgeHealth:
    status: str
    contract_version: str
    target_configuration: str
    provider: str
    published_entity_sets: int
    outbox_items: int
    ready_items: int
    blocked_items: int
    planned_documents: int
    post_documents: bool
    mapping_audit_ready: bool
    mapping_audit_errors: tuple[str, ...]
    mapping_audit_warnings: tuple[str, ...]


def check_health(
    ceh_client: CehSkladClient,
    fresh_client: FreshODataClient,
    mapping: TenantMapping,
    *,
    limit: int = 100,
    mapping_audit: TenantAuditReport | None = None,
) -> BridgeHealth:
    """Read-only readiness check. Не создает и не подтверждает документы."""
    profile = ceh_client.profile()
    entity_sets: list[ODataEntitySet] = fresh_client.entity_sets()
    mapping.validate_against_metadata(entity_sets)
    items: list[UnfOutboxItem] = ceh_client.outbox(max(1, min(limit, 100)))

    ready = 0
    blocked = 0
    planned_documents = 0
    for item in items:
        plan = build_plan(item)
        if plan.blocked:
            blocked += 1
        else:
            ready += 1
            planned_documents += len(plan.documents)

    audit_ready = mapping_audit is None or mapping_audit.status == "ready"
    audit_errors = mapping_audit.errors if mapping_audit is not None else ()
    audit_warnings = mapping_audit.warnings if mapping_audit is not None else ()
    return BridgeHealth(
        status="ready" if blocked == 0 and audit_ready else "degraded",
        contract_version=profile.contract_version,
        target_configuration=profile.target_configuration,
        provider=mapping.provider,
        published_entity_sets=len(entity_sets),
        outbox_items=len(items),
        ready_items=ready,
        blocked_items=blocked,
        planned_documents=planned_documents,
        post_documents=mapping.post_documents,
        mapping_audit_ready=audit_ready,
        mapping_audit_errors=audit_errors,
        mapping_audit_warnings=audit_warnings,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only health/readiness проверка bridge 1С:УНФ"
    )
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--ceh-url", default=os.getenv("CEH_API_URL"))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--allow-http-ceh", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ceh_key = os.getenv("CEH_1C_KEY")
    fresh_login = os.getenv("UNF_FRESH_LOGIN")
    fresh_password = os.getenv("UNF_FRESH_PASSWORD")
    if not args.ceh_url:
        raise SystemExit("Не задан --ceh-url или CEH_API_URL")
    if not ceh_key:
        raise SystemExit("Не задан CEH_1C_KEY")
    if not fresh_login or not fresh_password:
        raise SystemExit("Задайте UNF_FRESH_LOGIN и UNF_FRESH_PASSWORD через secret storage")

    mapping = TenantMapping.load(args.mapping)
    mapping_audit = audit_mapping_file(args.mapping)
    with CehSkladClient(
        args.ceh_url,
        ceh_key,
        allow_http=args.allow_http_ceh,
    ) as ceh_client, FreshODataClient(
        mapping.application_url,
        fresh_login,
        fresh_password,
    ) as fresh_client:
        health = check_health(
            ceh_client,
            fresh_client,
            mapping,
            limit=max(1, min(args.limit, 100)),
            mapping_audit=mapping_audit,
        )

    print(json.dumps(asdict(health), ensure_ascii=False, sort_keys=True))
    if health.status != "ready":
        sys.exit(3)


if __name__ == "__main__":
    main()
