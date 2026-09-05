from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .catalog_import import ProductFieldMapping
from .location_import import LocationImportMapping
from .operation_payloads import REQUIRED_HEADERS, REQUIRED_ROW_FIELDS
from .tenant_config import DOCUMENT_RESOURCES, TenantMapping


REQUIRED_OPERATION_CONSTANTS = (
    "organization_ref",
    "retail_customer_ref",
    "wholesale_customer_ref",
    "cashbox_ref",
    "cash_flow_item_ref",
)


@dataclass(frozen=True)
class TenantAuditReport:
    status: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    payload_schema_count: int
    location_allowlist_count: int
    representative_count: int
    payer_mapping_count: int
    post_documents: bool | None


def audit_mapping_data(data: dict[str, Any]) -> TenantAuditReport:
    errors: list[str] = []
    warnings: list[str] = []

    tenant: TenantMapping | None = None
    products: ProductFieldMapping | None = None
    locations: LocationImportMapping | None = None

    try:
        tenant = TenantMapping.from_dict(data)
    except ValueError as exc:
        errors.append(f"tenant: {exc}")

    try:
        products = ProductFieldMapping.from_dict(data)
    except ValueError as exc:
        errors.append(f"products: {exc}")

    try:
        locations = LocationImportMapping.from_dict(data)
    except ValueError as exc:
        errors.append(f"locations: {exc}")

    if products is not None:
        if products.deletion_policy == "ignore":
            warnings.append(
                "product_deletion_policy=ignore: DeletionMark УНФ не меняет активность товара; "
                "для production политика должна быть явно принята в UAT record"
            )
        elif products.deletion_policy == "block":
            warnings.append(
                "product_deletion_policy=block: помеченный товар остановит импорт до ручного решения"
            )

    if tenant is not None:
        missing_constants = [
            name for name in REQUIRED_OPERATION_CONSTANTS if not tenant.constants.get(name)
        ]
        if missing_constants:
            errors.append(
                "Не заданы обязательные constants для документов: " + ", ".join(missing_constants)
            )

        missing_schemas = [alias for alias in DOCUMENT_RESOURCES if alias not in tenant.payload_schemas]
        if missing_schemas:
            errors.append("Не заданы payload_schemas: " + ", ".join(missing_schemas))

        for alias in DOCUMENT_RESOURCES:
            schema = tenant.payload_schemas.get(alias)
            if schema is None:
                continue
            required_headers = REQUIRED_HEADERS.get(alias, set())
            missing_headers = sorted(required_headers - set(schema.header_fields))
            if missing_headers:
                errors.append(
                    f"payload_schemas.{alias} не содержит aliases шапки: "
                    + ", ".join(missing_headers)
                )

            required_rows = REQUIRED_ROW_FIELDS.get(alias)
            if required_rows is None:
                continue
            if schema.table is None:
                errors.append(f"payload_schemas.{alias} не содержит табличную часть")
                continue
            missing_rows = sorted(required_rows - set(schema.table.fields))
            if missing_rows:
                errors.append(
                    f"payload_schemas.{alias} не содержит aliases строки: "
                    + ", ".join(missing_rows)
                )

        if tenant.expected_metadata_structure_sha256 is None:
            warnings.append(
                "expected_metadata_structure_sha256 не задан: --execute будет заблокирован "
                "до фиксации принятой схемы УНФ"
            )
        if not tenant.post_documents:
            warnings.append(
                "post_documents=false: документы будут записываться без автоматического проведения"
            )

    representative_refs: list[str] = []
    location_count = 0
    if locations is not None:
        location_count = len(locations.allowlist)
        warehouse_count = sum(1 for item in locations.allowlist.values() if item.kind == "warehouse")
        representative_refs = [
            ref for ref, item in locations.allowlist.items() if item.kind == "representative"
        ]
        if warehouse_count == 0:
            errors.append("location_allowlist не содержит ни одного warehouse")
        if not representative_refs:
            errors.append("location_allowlist не содержит ни одного representative")

    payer_count = 0
    if tenant is not None:
        payer_count = len(tenant.representative_payer_refs)
        missing_payers = [
            ref for ref in representative_refs if not tenant.representative_payer_refs.get(ref)
        ]
        if missing_payers:
            errors.append(
                "Не заданы representative_payer_refs для складов представителей: "
                + ", ".join(missing_payers)
            )
        extra_payers = sorted(set(tenant.representative_payer_refs) - set(representative_refs))
        if extra_payers:
            warnings.append(
                "representative_payer_refs содержит записи вне representative allow-list: "
                + ", ".join(extra_payers)
            )

    return TenantAuditReport(
        status="ready" if not errors else "blocked",
        errors=tuple(errors),
        warnings=tuple(warnings),
        payload_schema_count=len(tenant.payload_schemas) if tenant is not None else 0,
        location_allowlist_count=location_count,
        representative_count=len(representative_refs),
        payer_mapping_count=payer_count,
        post_documents=tenant.post_documents if tenant is not None else None,
    )


def audit_mapping_file(path: str | Path) -> TenantAuditReport:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Tenant mapping должен быть JSON-объектом")
    return audit_mapping_data(raw)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Локальная проверка полноты tenant mapping перед UAT 1С:УНФ"
    )
    parser.add_argument("--mapping", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        report = audit_mapping_file(args.mapping)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        report = TenantAuditReport(
            status="blocked",
            errors=(str(exc),),
            warnings=(),
            payload_schema_count=0,
            location_allowlist_count=0,
            representative_count=0,
            payer_mapping_count=0,
            post_documents=None,
        )
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    if report.status != "ready":
        sys.exit(3)


if __name__ == "__main__":
    main()
