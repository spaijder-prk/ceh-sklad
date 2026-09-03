from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    InventoryBalance,
    Location,
    MoneyTransaction,
    MoneyTransactionKind,
    Product,
    StockDocument,
    StockDocumentKind,
    StockDocumentLine,
    StockMovement,
)
from .schemas import AdjustmentItemIn, MovementItemIn, PriceType


async def _ensure_balance_row(session: AsyncSession, location_id: UUID, product_id: UUID) -> None:
    """Атомарно создает нулевой остаток, если строки еще нет."""
    await session.execute(
        pg_insert(InventoryBalance)
        .values(location_id=location_id, product_id=product_id, quantity=Decimal("0"))
        .on_conflict_do_nothing(index_elements=["location_id", "product_id"])
    )


async def _locked_balance(session: AsyncSession, location_id: UUID, product_id: UUID) -> InventoryBalance:
    await _ensure_balance_row(session, location_id, product_id)
    balance = await session.scalar(
        select(InventoryBalance)
        .where(InventoryBalance.location_id == location_id, InventoryBalance.product_id == product_id)
        .with_for_update()
    )
    if balance is None:
        raise RuntimeError("Не удалось получить строку остатка после ее создания")
    return balance


async def _locked_transfer_balances(
    session: AsyncSession,
    source_location_id: UUID,
    destination_location_id: UUID,
    product_id: UUID,
) -> tuple[InventoryBalance, InventoryBalance]:
    """Блокирует обе строки в стабильном порядке, уменьшая риск взаимных блокировок."""
    location_ids = sorted((source_location_id, destination_location_id), key=str)
    for location_id in location_ids:
        await _ensure_balance_row(session, location_id, product_id)

    rows = list(
        await session.scalars(
            select(InventoryBalance)
            .where(
                InventoryBalance.product_id == product_id,
                InventoryBalance.location_id.in_(location_ids),
            )
            .order_by(InventoryBalance.location_id)
            .with_for_update()
        )
    )
    by_location = {row.location_id: row for row in rows}
    if source_location_id not in by_location or destination_location_id not in by_location:
        raise RuntimeError("Не удалось заблокировать строки остатков для перемещения")
    return by_location[source_location_id], by_location[destination_location_id]


def _aggregate_movement_items(items: list[MovementItemIn]) -> list[MovementItemIn]:
    quantities: dict[UUID, Decimal] = {}
    for item in items:
        quantities[item.product_id] = quantities.get(item.product_id, Decimal("0")) + item.quantity
    return [
        MovementItemIn(product_id=product_id, quantity=quantity)
        for product_id, quantity in sorted(quantities.items(), key=lambda pair: str(pair[0]))
    ]


def _aggregate_adjustment_items(items: list[AdjustmentItemIn]) -> list[AdjustmentItemIn]:
    quantities: dict[UUID, Decimal] = {}
    for item in items:
        quantities[item.product_id] = quantities.get(item.product_id, Decimal("0")) + item.quantity_delta
    return [
        AdjustmentItemIn(product_id=product_id, quantity_delta=quantity)
        for product_id, quantity in sorted(quantities.items(), key=lambda pair: str(pair[0]))
        if quantity != 0
    ]


def _check_document_key(document: StockDocument, kind: StockDocumentKind, payload_hash: str) -> None:
    if document.kind != kind or document.client_payload_hash != payload_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ключ операции уже использован с другим содержимым",
        )


async def _existing_document(
    session: AsyncSession,
    operation_key: str | None,
    payload_hash: str | None,
    kind: StockDocumentKind,
) -> StockDocument | None:
    if operation_key is None:
        return None
    if payload_hash is None:
        raise RuntimeError("Для идемпотентной операции требуется хэш содержимого")
    document = await session.scalar(
        select(StockDocument).where(StockDocument.client_operation_key == operation_key)
    )
    if document is not None:
        _check_document_key(document, kind, payload_hash)
    return document


async def _flush_new_document(
    session: AsyncSession,
    document: StockDocument,
    kind: StockDocumentKind,
) -> StockDocument | None:
    try:
        await session.flush()
        return None
    except IntegrityError as exc:
        if document.client_operation_key is None or document.client_payload_hash is None:
            raise
        operation_key = document.client_operation_key
        payload_hash = document.client_payload_hash
        await session.rollback()
        existing = await session.scalar(
            select(StockDocument).where(StockDocument.client_operation_key == operation_key)
        )
        if existing is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Конфликт при регистрации операции") from exc
        _check_document_key(existing, kind, payload_hash)
        return existing


def _check_money_key(transaction: MoneyTransaction, payload_hash: str) -> None:
    if transaction.kind != MoneyTransactionKind.CASH_HANDOVER or transaction.client_payload_hash != payload_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ключ операции уже использован с другим содержимым",
        )


async def create_transfer(
    session: AsyncSession,
    *,
    kind: StockDocumentKind,
    source_location_id: UUID,
    destination_location_id: UUID,
    items: list[MovementItemIn],
    comment: str | None,
    created_by_id: UUID | None = None,
    client_operation_key: str | None = None,
    client_payload_hash: str | None = None,
) -> StockDocument:
    if source_location_id == destination_location_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Источник и получатель совпадают")
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Не указаны товары")

    existing = await _existing_document(session, client_operation_key, client_payload_hash, kind)
    if existing is not None:
        return existing

    items = _aggregate_movement_items(items)
    document = StockDocument(
        kind=kind,
        source_location_id=source_location_id,
        destination_location_id=destination_location_id,
        created_by_id=created_by_id,
        comment=comment,
        client_operation_key=client_operation_key,
        client_payload_hash=client_payload_hash,
    )
    session.add(document)
    concurrent_existing = await _flush_new_document(session, document, kind)
    if concurrent_existing is not None:
        return concurrent_existing

    for item in items:
        source, destination = await _locked_transfer_balances(
            session, source_location_id, destination_location_id, item.product_id
        )
        if source.quantity < item.quantity:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Недостаточный остаток товара {item.product_id}")
        source.quantity -= item.quantity
        destination.quantity += item.quantity
        session.add(StockDocumentLine(document_id=document.id, product_id=item.product_id, quantity=item.quantity))
        session.add(StockMovement(document_id=document.id, location_id=source_location_id, product_id=item.product_id, quantity_delta=-item.quantity))
        session.add(StockMovement(document_id=document.id, location_id=destination_location_id, product_id=item.product_id, quantity_delta=item.quantity))

    await session.commit()
    return document


async def create_adjustment(
    session: AsyncSession,
    *,
    location_id: UUID,
    items: list[AdjustmentItemIn],
    comment: str,
    created_by_id: UUID | None,
    external_1c_id: str | None = None,
    mark_synced_1c: bool = False,
    commit: bool = True,
) -> StockDocument:
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Не указаны товары")
    items = _aggregate_adjustment_items(items)
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Корректировка не содержит изменений")

    document = StockDocument(
        kind=StockDocumentKind.ADJUSTMENT,
        created_by_id=created_by_id,
        comment=comment,
        external_1c_id=external_1c_id,
        synced_1c_at=datetime.now(UTC) if mark_synced_1c else None,
    )
    session.add(document)
    await session.flush()

    for item in items:
        balance = await _locked_balance(session, location_id, item.product_id)
        new_quantity = balance.quantity + item.quantity_delta
        if new_quantity < 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Корректировка уводит остаток товара {item.product_id} в минус")
        balance.quantity = new_quantity
        session.add(StockDocumentLine(document_id=document.id, product_id=item.product_id, quantity=abs(item.quantity_delta)))
        session.add(StockMovement(document_id=document.id, location_id=location_id, product_id=item.product_id, quantity_delta=item.quantity_delta))

    if commit:
        await session.commit()
    else:
        await session.flush()
    return document


async def create_sale(
    session: AsyncSession,
    *,
    representative_location_id: UUID,
    items: list[MovementItemIn],
    price_type: PriceType,
    comment: str | None,
    created_by_id: UUID | None = None,
    client_operation_key: str | None = None,
    client_payload_hash: str | None = None,
) -> StockDocument:
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Не указаны товары")

    existing = await _existing_document(session, client_operation_key, client_payload_hash, StockDocumentKind.SALE)
    if existing is not None:
        return existing

    items = _aggregate_movement_items(items)
    document = StockDocument(
        kind=StockDocumentKind.SALE,
        source_location_id=representative_location_id,
        created_by_id=created_by_id,
        comment=comment,
        client_operation_key=client_operation_key,
        client_payload_hash=client_payload_hash,
    )
    session.add(document)
    concurrent_existing = await _flush_new_document(session, document, StockDocumentKind.SALE)
    if concurrent_existing is not None:
        return concurrent_existing

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
    client_operation_key: str | None = None,
    client_payload_hash: str | None = None,
) -> MoneyTransaction:
    if client_operation_key is not None:
        if client_payload_hash is None:
            raise RuntimeError("Для идемпотентной операции требуется хэш содержимого")
        existing = await session.scalar(
            select(MoneyTransaction).where(MoneyTransaction.client_operation_key == client_operation_key)
        )
        if existing is not None:
            _check_money_key(existing, client_payload_hash)
            return existing

    representative = await session.scalar(
        select(Location).where(Location.id == representative_location_id).with_for_update()
    )
    if representative is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Торговый представитель не найден")

    debt = await representative_debt(session, representative_location_id)
    if amount > debt:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Сумма сдачи {amount} превышает текущую задолженность {debt}",
        )
    transaction = MoneyTransaction(
        representative_location_id=representative_location_id,
        kind=MoneyTransactionKind.CASH_HANDOVER,
        amount=-amount,
        created_by_id=created_by_id,
        comment=comment,
        client_operation_key=client_operation_key,
        client_payload_hash=client_payload_hash,
    )
    session.add(transaction)
    try:
        await session.flush()
    except IntegrityError as exc:
        if client_operation_key is None or client_payload_hash is None:
            raise
        await session.rollback()
        existing = await session.scalar(
            select(MoneyTransaction).where(MoneyTransaction.client_operation_key == client_operation_key)
        )
        if existing is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Конфликт при регистрации операции") from exc
        _check_money_key(existing, client_payload_hash)
        return existing
    await session.commit()
    return transaction


async def representative_debt(session: AsyncSession, representative_location_id: UUID) -> Decimal:
    value = await session.scalar(
        select(func.coalesce(func.sum(MoneyTransaction.amount), 0)).where(
            MoneyTransaction.representative_location_id == representative_location_id
        )
    )
    return Decimal(value)