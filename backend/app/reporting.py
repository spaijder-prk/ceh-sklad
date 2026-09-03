from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user, require_roles
from .database import get_session
from .models import (
    IntegrationExchangeLog,
    Location,
    LocationKind,
    MoneyTransaction,
    MoneyTransactionKind,
    Product,
    StockDocument,
    StockDocumentLine,
    StockMovement,
    User,
    UserRole,
)
from .services import representative_debt

router = APIRouter(prefix="/api/v1")


class StockOperationLineOut(BaseModel):
    product_id: UUID
    sku: str
    product_name: str
    unit_name: str
    quantity: Decimal
    unit_price: Decimal | None


class StockOperationOut(BaseModel):
    id: UUID
    kind: str
    source_location_id: UUID | None
    source_location_name: str | None
    destination_location_id: UUID | None
    destination_location_name: str | None
    created_by_name: str | None
    comment: str | None
    created_at: datetime
    synced_1c_at: datetime | None
    external_1c_id: str | None
    lines: list[StockOperationLineOut]


class MoneyOperationOut(BaseModel):
    id: UUID
    representative_location_id: UUID
    representative_name: str
    kind: str
    amount: Decimal
    stock_document_id: UUID | None
    created_by_name: str | None
    comment: str | None
    created_at: datetime
    synced_1c_at: datetime | None
    external_1c_id: str | None


class RepresentativeReportRow(BaseModel):
    representative_location_id: UUID
    representative_name: str
    sales_count: int
    sales_amount: Decimal
    cash_handover_amount: Decimal
    current_debt: Decimal


class IntegrationLogOut(BaseModel):
    id: UUID
    direction: str
    operation_key: str
    entity_type: str
    entity_internal_id: UUID | None
    external_1c_id: str | None
    status: str
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


@router.get("/operations/stock", response_model=list[StockOperationOut])
async def stock_operations(
    limit: int = 100,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[StockOperationOut]:
    limit = max(1, min(limit, 300))
    stmt = select(StockDocument).order_by(StockDocument.created_at.desc(), StockDocument.id.desc()).limit(limit)
    if user.role == UserRole.REPRESENTATIVE:
        stmt = stmt.where(
            StockDocument.id.in_(
                select(StockMovement.document_id).where(StockMovement.location_id == user.location_id)
            )
        )

    documents = list(await session.scalars(stmt))
    result: list[StockOperationOut] = []
    for document in documents:
        source = await session.get(Location, document.source_location_id) if document.source_location_id else None
        destination = await session.get(Location, document.destination_location_id) if document.destination_location_id else None
        creator = await session.get(User, document.created_by_id) if document.created_by_id else None
        line_rows = (
            await session.execute(
                select(StockDocumentLine, Product)
                .join(Product, Product.id == StockDocumentLine.product_id)
                .where(StockDocumentLine.document_id == document.id)
                .order_by(Product.name)
            )
        ).all()
        result.append(
            StockOperationOut(
                id=document.id,
                kind=document.kind.value,
                source_location_id=document.source_location_id,
                source_location_name=source.name if source else None,
                destination_location_id=document.destination_location_id,
                destination_location_name=destination.name if destination else None,
                created_by_name=creator.name if creator else None,
                comment=document.comment,
                created_at=document.created_at,
                synced_1c_at=document.synced_1c_at,
                external_1c_id=document.external_1c_id,
                lines=[
                    StockOperationLineOut(
                        product_id=product.id,
                        sku=product.sku,
                        product_name=product.name,
                        unit_name=product.unit_name,
                        quantity=line.quantity,
                        unit_price=line.unit_price,
                    )
                    for line, product in line_rows
                ],
            )
        )
    return result


@router.get("/operations/money", response_model=list[MoneyOperationOut])
async def money_operations(
    limit: int = 100,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MoneyOperationOut]:
    limit = max(1, min(limit, 300))
    stmt = select(MoneyTransaction).order_by(MoneyTransaction.created_at.desc(), MoneyTransaction.id.desc()).limit(limit)
    if user.role == UserRole.REPRESENTATIVE:
        stmt = stmt.where(MoneyTransaction.representative_location_id == user.location_id)

    transactions = list(await session.scalars(stmt))
    result: list[MoneyOperationOut] = []
    for transaction in transactions:
        representative = await session.get(Location, transaction.representative_location_id)
        creator = await session.get(User, transaction.created_by_id) if transaction.created_by_id else None
        result.append(
            MoneyOperationOut(
                id=transaction.id,
                representative_location_id=transaction.representative_location_id,
                representative_name=representative.name if representative else "Неизвестный представитель",
                kind=transaction.kind.value,
                amount=transaction.amount,
                stock_document_id=transaction.stock_document_id,
                created_by_name=creator.name if creator else None,
                comment=transaction.comment,
                created_at=transaction.created_at,
                synced_1c_at=transaction.synced_1c_at,
                external_1c_id=transaction.external_1c_id,
            )
        )
    return result


@router.get("/reports/representatives", response_model=list[RepresentativeReportRow])
async def representatives_report(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> list[RepresentativeReportRow]:
    representatives = list(
        await session.scalars(
            select(Location).where(Location.kind == LocationKind.REPRESENTATIVE).order_by(Location.name)
        )
    )
    result: list[RepresentativeReportRow] = []
    for representative in representatives:
        stmt = select(MoneyTransaction).where(
            MoneyTransaction.representative_location_id == representative.id
        )
        if date_from is not None:
            stmt = stmt.where(MoneyTransaction.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(MoneyTransaction.created_at <= date_to)
        rows = list(await session.scalars(stmt))
        sales = [row for row in rows if row.kind == MoneyTransactionKind.SALE]
        handovers = [row for row in rows if row.kind == MoneyTransactionKind.CASH_HANDOVER]
        result.append(
            RepresentativeReportRow(
                representative_location_id=representative.id,
                representative_name=representative.name,
                sales_count=len(sales),
                sales_amount=sum((row.amount for row in sales), Decimal("0")),
                cash_handover_amount=sum((-row.amount for row in handovers), Decimal("0")),
                current_debt=await representative_debt(session, representative.id),
            )
        )
    return result


@router.get("/admin/integration-1c/logs", response_model=list[IntegrationLogOut])
async def integration_logs(
    limit: int = 100,
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> list[IntegrationExchangeLog]:
    limit = max(1, min(limit, 300))
    return list(
        await session.scalars(
            select(IntegrationExchangeLog)
            .order_by(IntegrationExchangeLog.created_at.desc(), IntegrationExchangeLog.id.desc())
            .limit(limit)
        )
    )
