from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    InventoryBalance,
    MoneyTransaction,
    MoneyTransactionKind,
    Product,
    StockDocument,
    StockDocumentKind,
    StockDocumentLine,
    StockMovement,
)
from .schemas import MovementItemIn, PriceType


async def _locked_balance(session: AsyncSession, location_id: UUID, product_id: UUID) -> InventoryBalance:
    stmt = (
        select(InventoryBalance)
        .where(InventoryBalance.location_id == location_id, InventoryBalance.product_id == product_id)
        .with_for_update()
    )
    balance = await session.scalar(stmt)
    if balance is None:
        balance = InventoryBalance(location_id=location_id, product_id=product_id, quantity=Decimal("0"))
        session.add(balance)
        await session.flush()
    return balance


async def create_transfer(
    session: AsyncSession,
    *,
    kind: StockDocumentKind,
    source_location_id: UUID,
    destination_location_id: UUID,
    items: list[MovementItemIn],
    comment: str | None,
    created_by_id: UUID | None = None,
) -> StockDocument:
    if source_location_id == destination_location_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Источник и получатель совпадают")
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Не указаны товары")

    document = StockDocument(
        kind=kind,
        source_location_id=source_location_id,
        destination_location_id=destination_location_id,
        created_by_id=created_by_id,
        comment=comment,
    )
    session.add(document)
    await session.flush()

    for item in items:
        source = await _locked_balance(session, source_location_id, item.product_id)
        destination = await _locked_balance(session, destination_location_id, item.product_id)
        if source.quantity < item.quantity:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Недостаточный остаток товара {item.product_id}")
        source.quantity -= item.quantity
        destination.quantity += item.quantity
        session.add(StockDocumentLine(document_id=document.id, product_id=item.product_id, quantity=item.quantity))
        session.add(StockMovement(document_id=document.id, location_id=source_location_id, product_id=item.product_id, quantity_delta=-item.quantity))
        session.add(StockMovement(document_id=document.id, location_id=destination_location_id, product_id=item.product_id, quantity_delta=item.quantity))

    await session.commit()
    return document


async def create_sale(
    session: AsyncSession,
    *,
    representative_location_id: UUID,
    items: list[MovementItemIn],
    price_type: PriceType,
    comment: str | None,
    created_by_id: UUID | None = None,
) -> StockDocument:
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Не указаны товары")

    document = StockDocument(
        kind=StockDocumentKind.SALE,
        source_location_id=representative_location_id,
        created_by_id=created_by_id,
        comment=comment,
    )
    session.add(document)
    await session.flush()

    total = Decimal("0")
    for item in items:
        balance = await _locked_balance(session, representative_location_id, item.product_id)
        if balance.quantity < item.quantity:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Недостаточный остаток товара {item.product_id} у представителя")
        product = await session.get(Product, item.product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")
        unit_price = product.retail_price if price_type == PriceType.RETAIL else product.wholesale_price
        balance.quantity -= item.quantity
        total += item.quantity * unit_price
        session.add(StockDocumentLine(document_id=document.id, product_id=item.product_id, quantity=item.quantity, unit_price=unit_price))
        session.add(StockMovement(document_id=document.id, location_id=representative_location_id, product_id=item.product_id, quantity_delta=-item.quantity))

    session.add(
        MoneyTransaction(
            representative_location_id=representative_location_id,
            kind=MoneyTransactionKind.SALE,
            amount=total,
            stock_document_id=document.id,
            created_by_id=created_by_id,
            comment=comment,
        )
    )
    await session.commit()
    return document


async def create_cash_handover(
    session: AsyncSession,
    *,
    representative_location_id: UUID,
    amount: Decimal,
    comment: str | None,
    created_by_id: UUID | None = None,
) -> MoneyTransaction:
    transaction = MoneyTransaction(
        representative_location_id=representative_location_id,
        kind=MoneyTransactionKind.CASH_HANDOVER,
        amount=-amount,
        created_by_id=created_by_id,
        comment=comment,
    )
    session.add(transaction)
    await session.commit()
    return transaction


async def representative_debt(session: AsyncSession, representative_location_id: UUID) -> Decimal:
    value = await session.scalar(
        select(func.coalesce(func.sum(MoneyTransaction.amount), 0)).where(
            MoneyTransaction.representative_location_id == representative_location_id
        )
    )
    return Decimal(value)
