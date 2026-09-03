from __future__ import annotations

import asyncio
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select

from app.database import SessionFactory
from app.models import (
    InventoryBalance,
    Location,
    LocationKind,
    MoneyTransaction,
    Product,
    StockDocument,
    StockDocumentKind,
    StockDocumentLine,
    StockMovement,
)
from app.schemas import MovementItemIn, PriceType
from app.services import create_cash_handover, create_sale, create_transfer, representative_debt


async def _product_and_locations(session):
    warehouse = Location(name="Основной склад", kind=LocationKind.WAREHOUSE)
    second_warehouse = Location(name="Склад 2", kind=LocationKind.WAREHOUSE)
    representative = Location(name="Представитель Иван", kind=LocationKind.REPRESENTATIVE)
    product = Product(
        sku="T-001",
        name="Тестовый товар",
        unit_name="шт",
        retail_price=Decimal("100.00"),
        wholesale_price=Decimal("80.00"),
    )
    session.add_all([warehouse, second_warehouse, representative, product])
    await session.flush()
    return warehouse, second_warehouse, representative, product


async def test_transfer_moves_stock_and_writes_ledger(session):
    warehouse, second_warehouse, _, product = await _product_and_locations(session)
    session.add(InventoryBalance(location_id=warehouse.id, product_id=product.id, quantity=Decimal("10")))
    await session.commit()

    document = await create_transfer(
        session,
        kind=StockDocumentKind.TRANSFER,
        source_location_id=warehouse.id,
        destination_location_id=second_warehouse.id,
        items=[MovementItemIn(product_id=product.id, quantity=Decimal("3"))],
        comment="Тестовое перемещение",
    )

    source = await session.scalar(select(InventoryBalance).where(InventoryBalance.location_id == warehouse.id))
    destination = await session.scalar(select(InventoryBalance).where(InventoryBalance.location_id == second_warehouse.id))
    movement_count = await session.scalar(select(func.count(StockMovement.id)).where(StockMovement.document_id == document.id))

    assert source is not None and source.quantity == Decimal("7.000")
    assert destination is not None and destination.quantity == Decimal("3.000")
    assert movement_count == 2


async def test_sale_uses_retail_price_and_cash_handover_reduces_debt(session):
    _, _, representative, product = await _product_and_locations(session)
    session.add(InventoryBalance(location_id=representative.id, product_id=product.id, quantity=Decimal("5")))
    await session.commit()

    document = await create_sale(
        session,
        representative_location_id=representative.id,
        items=[MovementItemIn(product_id=product.id, quantity=Decimal("2"))],
        price_type=PriceType.RETAIL,
        comment="Продажа",
    )

    line = await session.scalar(select(StockDocumentLine).where(StockDocumentLine.document_id == document.id))
    balance = await session.scalar(
        select(InventoryBalance).where(
            InventoryBalance.location_id == representative.id,
            InventoryBalance.product_id == product.id,
        )
    )
    assert line is not None and line.unit_price == Decimal("100.00")
    assert balance is not None and balance.quantity == Decimal("3.000")
    assert await representative_debt(session, representative.id) == Decimal("200.00")

    await create_cash_handover(
        session,
        representative_location_id=representative.id,
        amount=Decimal("150.00"),
        comment="Сдача выручки",
    )
    assert await representative_debt(session, representative.id) == Decimal("50.00")
    assert await session.scalar(select(func.count(MoneyTransaction.id))) == 2


async def test_two_simultaneous_sales_cannot_write_off_same_last_unit(session):
    _, _, representative, product = await _product_and_locations(session)
    session.add(InventoryBalance(location_id=representative.id, product_id=product.id, quantity=Decimal("1")))
    await session.commit()
    representative_id = representative.id
    product_id = product.id

    async def sell_once():
        async with SessionFactory() as concurrent_session:
            try:
                return await create_sale(
                    concurrent_session,
                    representative_location_id=representative_id,
                    items=[MovementItemIn(product_id=product_id, quantity=Decimal("1"))],
                    price_type=PriceType.WHOLESALE,
                    comment="Конкурентная продажа",
                )
            except Exception:
                await concurrent_session.rollback()
                raise

    results = await asyncio.gather(sell_once(), sell_once(), return_exceptions=True)
    errors = [result for result in results if isinstance(result, Exception)]
    successes = [result for result in results if isinstance(result, StockDocument)]

    assert len(successes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], HTTPException)
    assert errors[0].status_code == 409

    async with SessionFactory() as check_session:
        balance = await check_session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.location_id == representative_id,
                InventoryBalance.product_id == product_id,
            )
        )
        sale_count = await check_session.scalar(
            select(func.count(StockDocument.id)).where(StockDocument.kind == StockDocumentKind.SALE)
        )
        assert balance is not None and balance.quantity == Decimal("0.000")
        assert sale_count == 1
