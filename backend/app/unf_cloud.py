from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .integration_1c import require_1c_key
from .models import (
    Location,
    MoneyTransaction,
    MoneyTransactionKind,
    Product,
    StockDocument,
    StockDocumentKind,
    StockDocumentLine,
    StockMovement,
)


router = APIRouter(
    prefix="/api/v1/integration/1c/unf",
    tags=["1С:УНФ Cloud"],
    dependencies=[Depends(require_1c_key)],
)


class UnfProfileOut(BaseModel):
    contract_version: str
    target_configuration: str
    deployment: str
    recommended_transport: str
    generic_import_base: str
    confirm_export_path: str
    confirm_export_batch_path: str
    representative_inventory_strategy: str
    mappings: dict[str, str]


class UnfOutboxLine(BaseModel):
    product_id: UUID
    product_external_1c_id: str | None
    sku: str
    quantity: Decimal
    quantity_delta: Decimal | None = None
    unit_price: Decimal | None = None


class UnfOutboxItem(BaseModel):
    entity_type: Literal["stock_document", "cash_handover"]
    internal_id: UUID
    kind: str
    created_at: datetime
    unf_document: str
    unf_operation: str
    ready_for_unf: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    requires_split: bool = False
    sale_price_type: Literal["retail", "wholesale"] | None = None
    source_location_external_1c_id: str | None = None
    destination_location_external_1c_id: str | None = None
    adjustment_location_external_1c_id: str | None = None
    representative_external_1c_id: str | None = None
    amount: Decimal | None = None
    comment: str | None = None
    lines: list[UnfOutboxLine] = Field(default_factory=list)


@router.get("/profile", response_model=UnfProfileOut)
async def unf_profile() -> UnfProfileOut:
    """Стабильный контракт для bridge между ceh-sklad и облачной 1С:УНФ."""
    return UnfProfileOut(
        contract_version="unf-cloud-v2",
        target_configuration="1С:Управление нашей фирмой",
        deployment="cloud",
        recommended_transport="external_bridge",
        generic_import_base="/api/v1/integration/1c",
        confirm_export_path="/api/v1/integration/1c/confirm-export",
        confirm_export_batch_path="/api/v1/integration/1c/confirm-export-batch",
        representative_inventory_strategy="Отдельный склад УНФ для каждого торгового представителя",
        mappings={
            StockDocumentKind.TRANSFER.value: "Перемещение запасов",
            StockDocumentKind.ISSUE_TO_REPRESENTATIVE.value: "Перемещение запасов",
            StockDocumentKind.REPRESENTATIVE_RETURN.value: "Перемещение запасов",
            StockDocumentKind.SALE.value: "Расходная накладная",
            StockDocumentKind.ADJUSTMENT.value: "Оприходование запасов / Списание запасов",
            MoneyTransactionKind.CASH_HANDOVER.value: "Поступление в кассу",
        },
    )


def _stock_target(kind: StockDocumentKind, deltas: list[Decimal]) -> tuple[str, str, bool]:
    if kind in {
        StockDocumentKind.TRANSFER,
        StockDocumentKind.ISSUE_TO_REPRESENTATIVE,
        StockDocumentKind.REPRESENTATIVE_RETURN,
    }:
        return "Перемещение запасов", "Перемещение между складами УНФ", False
    if kind == StockDocumentKind.SALE:
        return "Расходная накладная", "Продажа со склада торгового представителя", False
    if kind == StockDocumentKind.ADJUSTMENT:
        has_positive = any(value > 0 for value in deltas)
        has_negative = any(value < 0 for value in deltas)
        if has_positive and has_negative:
            return (
                "Оприходование запасов + Списание запасов",
                "Смешанную корректировку необходимо разделить на два документа УНФ",
                True,
            )
        if has_positive:
            return "Оприходование запасов", "Положительная корректировка остатка", False
        return "Списание запасов", "Отрицательная корректировка остатка", False
    return kind.value, "Требуется согласовать сопоставление с УНФ", False


@router.get("/outbox", response_model=list[UnfOutboxItem])
async def unf_outbox(limit: int = 50, session: AsyncSession = Depends(get_session)) -> list[UnfOutboxItem]:
    """Outbox с готовым сопоставлением документов ceh-sklad -> 1С:УНФ Cloud."""
    limit = max(1, min(limit, 100))
    result: list[UnfOutboxItem] = []
    documents = list(
        await session.scalars(
            select(StockDocument)
            .where(StockDocument.synced_1c_at.is_(None), StockDocument.external_1c_id.is_(None))
            .order_by(StockDocument.created_at, StockDocument.id)
            .limit(limit)
        )
    )

    for document in documents:
        source = await session.get(Location, document.source_location_id) if document.source_location_id else None
        destination = await session.get(Location, document.destination_location_id) if document.destination_location_id else None
        line_rows = (
            await session.execute(
                select(StockDocumentLine, Product)
                .join(Product, Product.id == StockDocumentLine.product_id)
                .where(StockDocumentLine.document_id == document.id)
                .order_by(Product.sku)
            )
        ).all()

        adjustment_deltas: dict[UUID, Decimal] = {}
        adjustment_location: Location | None = None
        if document.kind == StockDocumentKind.ADJUSTMENT:
            movement_rows = (
                await session.execute(
                    select(
                        StockMovement.location_id,
                        StockMovement.product_id,
                        func.sum(StockMovement.quantity_delta),
                    )
                    .where(StockMovement.document_id == document.id)
                    .group_by(StockMovement.location_id, StockMovement.product_id)
                )
            ).all()
            location_ids = {row[0] for row in movement_rows}
            if len(location_ids) == 1:
                adjustment_location = await session.get(Location, next(iter(location_ids)))
            for _, product_id, delta in movement_rows:
                adjustment_deltas[product_id] = Decimal(delta)

        deltas = list(adjustment_deltas.values())
        unf_document, unf_operation, requires_split = _stock_target(document.kind, deltas)
        reasons: list[str] = []
        if document.kind in {
            StockDocumentKind.TRANSFER,
            StockDocumentKind.ISSUE_TO_REPRESENTATIVE,
            StockDocumentKind.REPRESENTATIVE_RETURN,
        }:
            if source is None or not source.external_1c_id:
                reasons.append("Не сопоставлен склад-источник с УНФ")
            if destination is None or not destination.external_1c_id:
                reasons.append("Не сопоставлен склад-получатель с УНФ")
        elif document.kind == StockDocumentKind.SALE:
            if source is None or not source.external_1c_id:
                reasons.append("Не сопоставлен склад торгового представителя с УНФ")
            if document.sale_price_type not in {"retail", "wholesale"}:
                reasons.append("У продажи не сохранен тип цены retail/wholesale; legacy-продажу нельзя экспортировать автоматически")
        elif document.kind == StockDocumentKind.ADJUSTMENT:
            if adjustment_location is None or not adjustment_location.external_1c_id:
                reasons.append("Не сопоставлено место корректировки с УНФ")
            if not deltas:
                reasons.append("Не найдены движения корректировки")

        lines: list[UnfOutboxLine] = []
        for line, product in line_rows:
            if not product.external_1c_id:
                reasons.append(f"Товар {product.sku} не сопоставлен с номенклатурой УНФ")
            lines.append(
                UnfOutboxLine(
                    product_id=product.id,
                    product_external_1c_id=product.external_1c_id,
                    sku=product.sku,
                    quantity=line.quantity,
                    quantity_delta=adjustment_deltas.get(product.id),
                    unit_price=line.unit_price,
                )
            )

        result.append(
            UnfOutboxItem(
                entity_type="stock_document",
                internal_id=document.id,
                kind=document.kind.value,
                created_at=document.created_at,
                unf_document=unf_document,
                unf_operation=unf_operation,
                ready_for_unf=not reasons,
                blocking_reasons=list(dict.fromkeys(reasons)),
                requires_split=requires_split,
                sale_price_type=(
                    document.sale_price_type
                    if document.sale_price_type in {"retail", "wholesale"}
                    else None
                ),
                source_location_external_1c_id=source.external_1c_id if source else None,
                destination_location_external_1c_id=destination.external_1c_id if destination else None,
                adjustment_location_external_1c_id=(
                    adjustment_location.external_1c_id if adjustment_location else None
                ),
                comment=document.comment,
                lines=lines,
            )
        )

    remaining = limit - len(result)
    if remaining > 0:
        handovers = list(
            await session.scalars(
                select(MoneyTransaction)
                .where(
                    MoneyTransaction.kind == MoneyTransactionKind.CASH_HANDOVER,
                    MoneyTransaction.synced_1c_at.is_(None),
                    MoneyTransaction.external_1c_id.is_(None),
                )
                .order_by(MoneyTransaction.created_at, MoneyTransaction.id)
                .limit(remaining)
            )
        )
        for transaction in handovers:
            representative = await session.get(Location, transaction.representative_location_id)
            reasons = [] if representative and representative.external_1c_id else [
                "Не сопоставлен склад торгового представителя с УНФ"
            ]
            result.append(
                UnfOutboxItem(
                    entity_type="cash_handover",
                    internal_id=transaction.id,
                    kind=transaction.kind.value,
                    created_at=transaction.created_at,
                    unf_document="Поступление в кассу",
                    unf_operation="Прием наличной выручки от торгового представителя",
                    ready_for_unf=not reasons,
                    blocking_reasons=reasons,
                    representative_external_1c_id=(
                        representative.external_1c_id if representative else None
                    ),
                    amount=-transaction.amount,
                    comment=transaction.comment,
                )
            )

    return result
