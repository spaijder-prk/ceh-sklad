from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .catalog_import import ProductFieldMapping
from .ceh_client import CehSkladClient
from .evidence import metadata_structure_sha256, sha256_file
from .location_import import LocationImportMapping
from .models import UnfOutboxItem
from .odata import FreshODataClient, ODataEntitySet
from .operation_payloads import UnfOperationPayloadFactory
from .planner import build_plan
from .tenant_audit import TenantAuditReport, audit_mapping_file
from .tenant_config import TenantMapping


REFERENCE_CONSTANT_RESOURCES = {
    "retail_price_type_ref": "price_types",
    "wholesale_price_type_ref": "price_types",
    "organization_ref": "organizations",
    "retail_customer_ref": "counterparties",
    "wholesale_customer_ref": "counterparties",
}


@dataclass(frozen=True)
class BridgeHealth:
    status: str
    backend_readiness_checked: bool
    backend_ready: bool
    backend_database: str | None
    backend_schema_revision: str | None
    contract_version: str
    target_configuration: str
    provider: str
    mapping_sha256: str | None
    metadata_structure_sha256: str
    expected_metadata_structure_sha256: str | None
    metadata_structure_matches_expected: bool
    published_entity_sets: int
    outbox_items: int
    ready_items: int
    blocked_items: int
    planned_documents: int
    payload_validated_documents: int
    payload_validation_errors: tuple[str, ...]
    catalog_mapping_ready: bool
    catalog_mapping_errors: tuple[str, ...]
    reference_objects_ready: bool
    reference_validation_errors: tuple[str, ...]
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
    product_mapping: ProductFieldMapping | None = None,
    location_mapping: LocationImportMapping | None = None,
    validate_reference_objects: bool = False,
    backend_readiness: dict[str, Any] | None = None,
    mapping_sha256: str | None = None,
) -> BridgeHealth:
    """Read-only readiness check. Не создает и не подтверждает документы."""
    backend_checked = backend_readiness is not None
    backend_database = (
        str(backend_readiness.get("database"))
        if backend_readiness and backend_readiness.get("database") is not None
        else None
    )
    backend_schema_revision = (
        str(backend_readiness.get("schema_revision"))
        if backend_readiness and backend_readiness.get("schema_revision") is not None
        else None
    )
    backend_ready = (
        not backend_checked
        or (
            backend_readiness is not None
            and backend_readiness.get("status") == "ready"
            and backend_database == "ok"
            and bool(backend_schema_revision)
        )
    )

    profile = ceh_client.profile()
    entity_sets: list[ODataEntitySet] = fresh_client.entity_sets()
    mapping.validate_against_metadata(entity_sets)
    metadata_digest = metadata_structure_sha256(mapping.application_url, entity_sets)
    expected_metadata_digest = mapping.expected_metadata_structure_sha256
    metadata_matches_expected = (
        expected_metadata_digest is None or metadata_digest == expected_metadata_digest
    )

    catalog_errors: list[str] = []
    if product_mapping is not None:
        try:
            product_mapping.validate_against_metadata(entity_sets, mapping.resources["products"])
        except ValueError as exc:
            catalog_errors.append(f"products: {exc}")
    if location_mapping is not None:
        try:
            location_mapping.validate_against_metadata(entity_sets, mapping.resources["warehouses"])
        except ValueError as exc:
            catalog_errors.append(f"locations: {exc}")

    audit_ready = mapping_audit is None or mapping_audit.status == "ready"
    audit_errors = mapping_audit.errors if mapping_audit is not None else ()
    audit_warnings = mapping_audit.warnings if mapping_audit is not None else ()

    reference_errors: list[str] = []
    if validate_reference_objects and audit_ready:
        for constant_name, resource_alias in REFERENCE_CONSTANT_RESOURCES.items():
            ref_key = mapping.constants.get(constant_name)
            if not ref_key:
                continue
            resource = mapping.resources[resource_alias]
            if fresh_client.find_one_by_guid(resource, ref_key) is None:
                reference_errors.append(
                    f"constants.{constant_name}: Ref_Key {ref_key} не найден в {resource}"
                )

        for check in mapping.reference_checks:
            if fresh_client.find_one_by_guid(check.resource, check.ref_key) is None:
                reference_errors.append(
                    f"reference_checks.{check.name}: Ref_Key {check.ref_key} не найден в {check.resource}"
                )

    items: list[UnfOutboxItem] = ceh_client.outbox(max(1, min(limit, 100)))
    payload_factory = (
        UnfOperationPayloadFactory(mapping)
        if mapping_audit is not None and audit_ready
        else None
    )

    ready = 0
    blocked = 0
    planned_documents = 0
    payload_validated_documents = 0
    payload_errors: list[str] = []
    for item in items:
        plan = build_plan(item)
        if plan.blocked:
            blocked += 1
            continue

        planned_documents += len(plan.documents)
        item_payload_ready = True
        if payload_factory is not None:
            for document in plan.documents:
                try:
                    payload_factory(item, document)
                    payload_validated_documents += 1
                except (ValueError, KeyError, TypeError) as exc:
                    item_payload_ready = False
                    payload_errors.append(f"{item.internal_id}: {exc}")
        if item_payload_ready:
            ready += 1
        else:
            blocked += 1

    catalog_ready = not catalog_errors
    references_ready = not reference_errors
    is_ready = (
        backend_ready
        and blocked == 0
        and audit_ready
        and not payload_errors
        and catalog_ready
        and references_ready
        and metadata_matches_expected
    )
    return BridgeHealth(
        status="ready" if is_ready else "degraded",
        backend_readiness_checked=backend_checked,
        backend_ready=backend_ready,
        backend_database=backend_database,
        backend_schema_revision=backend_schema_revision,
        contract_version=profile.contract_version,
        target_configuration=profile.target_configuration,
        provider=mapping.provider,
        mapping_sha256=mapping_sha256,
        metadata_structure_sha256=metadata_digest,
        expected_metadata_structure_sha256=expected_metadata_digest,
        metadata_structure_matches_expected=metadata_matches_expected,
        published_entity_sets=len(entity_sets),
        outbox_items=len(items),
        ready_items=ready,
        blocked_items=blocked,
        planned_documents=planned_documents,
        payload_validated_documents=payload_validated_documents,
        payload_validation_errors=tuple(payload_errors),
        catalog_mapping_ready=catalog_ready,
        catalog_mapping_errors=tuple(catalog_errors),
        reference_objects_ready=references_ready,
        reference_validation_errors=tuple(reference_errors),
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

    mapping_digest = sha256_file(args.mapping)
    mapping = TenantMapping.load(args.mapping)
    mapping_audit = audit_mapping_file(args.mapping)
    product_mapping = (
        ProductFieldMapping.load(args.mapping) if mapping_audit.status == "ready" else None
    )
    location_mapping = (
        LocationImportMapping.load(args.mapping) if mapping_audit.status == "ready" else None
    )
    with CehSkladClient(
        args.ceh_url,
        ceh_key,
        allow_http=args.allow_http_ceh,
    ) as ceh_client, FreshODataClient(
        mapping.application_url,
        fresh_login,
        fresh_password,
    ) as fresh_client:
        backend_readiness = ceh_client.readiness()
        health = check_health(
            ceh_client,
            fresh_client,
            mapping,
            limit=max(1, min(args.limit, 100)),
            mapping_audit=mapping_audit,
            product_mapping=product_mapping,
            location_mapping=location_mapping,
            validate_reference_objects=True,
            backend_readiness=backend_readiness,
            mapping_sha256=mapping_digest,
        )

    print(json.dumps(asdict(health), ensure_ascii=False, sort_keys=True))
    if health.status != "ready":
        sys.exit(3)


if __name__ == "__main__":
    main()
