from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class UnfProfile:
    contract_version: str
    target_configuration: str
    deployment: str
    confirm_export_path: str
    confirm_export_batch_path: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "UnfProfile":
        return cls(
            contract_version=str(data["contract_version"]),
            target_configuration=str(data["target_configuration"]),
            deployment=str(data["deployment"]),
            confirm_export_path=str(data["confirm_export_path"]),
            confirm_export_batch_path=str(data["confirm_export_batch_path"]),
        )


@dataclass(frozen=True)
class UnfLine:
    product_external_1c_id: str | None
    sku: str
    quantity: Decimal
    quantity_delta: Decimal | None
    unit_price: Decimal | None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "UnfLine":
        return cls(
            product_external_1c_id=data.get("product_external_1c_id"),
            sku=str(data["sku"]),
            quantity=Decimal(str(data["quantity"])),
            quantity_delta=(
                Decimal(str(data["quantity_delta"]))
                if data.get("quantity_delta") is not None
                else None
            ),
            unit_price=(Decimal(str(data["unit_price"])) if data.get("unit_price") is not None else None),
        )


@dataclass(frozen=True)
class UnfOutboxItem:
    entity_type: str
    internal_id: str
    kind: str
    unf_document: str
    unf_operation: str
    ready_for_unf: bool
    blocking_reasons: tuple[str, ...]
    requires_split: bool
    source_location_external_1c_id: str | None
    destination_location_external_1c_id: str | None
    adjustment_location_external_1c_id: str | None
    representative_external_1c_id: str | None
    amount: Decimal | None
    comment: str | None
    lines: tuple[UnfLine, ...]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "UnfOutboxItem":
        return cls(
            entity_type=str(data["entity_type"]),
            internal_id=str(data["internal_id"]),
            kind=str(data["kind"]),
            unf_document=str(data["unf_document"]),
            unf_operation=str(data["unf_operation"]),
            ready_for_unf=bool(data["ready_for_unf"]),
            blocking_reasons=tuple(str(value) for value in data.get("blocking_reasons", [])),
            requires_split=bool(data.get("requires_split", False)),
            source_location_external_1c_id=data.get("source_location_external_1c_id"),
            destination_location_external_1c_id=data.get("destination_location_external_1c_id"),
            adjustment_location_external_1c_id=data.get("adjustment_location_external_1c_id"),
            representative_external_1c_id=data.get("representative_external_1c_id"),
            amount=Decimal(str(data["amount"])) if data.get("amount") is not None else None,
            comment=data.get("comment"),
            lines=tuple(UnfLine.from_json(row) for row in data.get("lines", [])),
        )
