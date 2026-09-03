from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import UnfOutboxItem


@dataclass(frozen=True)
class PlannedDocument:
    external_key: str
    unf_document: str
    operation: str
    line_skus: tuple[str, ...]


@dataclass(frozen=True)
class PlanResult:
    item: UnfOutboxItem
    documents: tuple[PlannedDocument, ...]
    blocked: bool


def stable_external_key(item: UnfOutboxItem, suffix: str | None = None) -> str:
    value = f"ceh-sklad:{item.entity_type}:{item.internal_id}"
    return f"{value}:{suffix}" if suffix else value


def build_plan(item: UnfOutboxItem) -> PlanResult:
    if not item.ready_for_unf:
        return PlanResult(item=item, documents=(), blocked=True)

    if item.requires_split:
        positive = tuple(
            line.sku for line in item.lines if (line.quantity_delta or Decimal("0")) > 0
        )
        negative = tuple(
            line.sku for line in item.lines if (line.quantity_delta or Decimal("0")) < 0
        )
        if not positive or not negative:
            raise ValueError("requires_split=true, но корректировка не содержит обеих групп дельт")
        return PlanResult(
            item=item,
            documents=(
                PlannedDocument(
                    external_key=stable_external_key(item, "receipt"),
                    unf_document="Оприходование запасов",
                    operation="Положительная часть смешанной корректировки",
                    line_skus=positive,
                ),
                PlannedDocument(
                    external_key=stable_external_key(item, "writeoff"),
                    unf_document="Списание запасов",
                    operation="Отрицательная часть смешанной корректировки",
                    line_skus=negative,
                ),
            ),
            blocked=False,
        )

    return PlanResult(
        item=item,
        documents=(
            PlannedDocument(
                external_key=stable_external_key(item),
                unf_document=item.unf_document,
                operation=item.unf_operation,
                line_skus=tuple(line.sku for line in item.lines),
            ),
        ),
        blocked=False,
    )
