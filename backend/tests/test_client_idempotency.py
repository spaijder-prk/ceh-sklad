from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import InventoryBalance, Location, LocationKind, MoneyTransaction, MoneyTransactionKind, Product, StockDocument, StockDocumentKind
from app.schemas import MovementItemIn, PriceType
from app.services import create_cash_handover, create_sale, representative_debt


async def test_repeated_sale_key_does_not_double_write_off(session):
    representative = Location(name="Представитель идемпотентность", kind=LocationKind.REPRESENTATIVE)
    product = Product(
        sku="IDEMP-001",
        name="Товар идемпотентность",
        unit_name="шт",
        retail_price=Decimal("100.00"),
        wholesale_price=Decimal("80.00"),
    )
    session.add_all([representative, product])
    await session.flush()
    session.add(InventoryBalance(location_id=representative.id, product_id=product.id, quantity=Decimal("2")))
    await session.commit()

    params = dict(
        representative_location_id=representative.id,
        items=[MovementItemIn(product_id=product.id, quantity=Decimal("1"))],
        price_type=PriceType.RETAIL,
        comment="Мобильная продажа",
        client_operation_key="android:sale:00000001",
        client_payload_hash="a" * 64,
    )
    first = await create_sale(session, **params)
    second = await create_sale(session, **params)

    assert first.id == second.id
    balance = await session.scalar(
        select(InventoryBalance).where(
            InventoryBalance.location_id == representative.id,
            InventoryBalance.product_id == product.id,
        )
    )
    assert balance is not None and balance.quantity == Decimal("1.000")
    assert await session.scalar(select(func.count(StockDocument.id)).where(StockDocument.kind == StockDocumentKind.SALE)) == 1
    assert await session.scalar(select(func.count(MoneyTransaction.id)).where(MoneyTransaction.kind == MoneyTransactionKind.SALE)) == 1

    with pytest.raises(HTTPException) as conflict:
        await create_sale(session, **{**params, "client_payload_hash": "b" * 64})
    assert conflict.value.status_code == 409


async def test_repeated_cash_handover_key_reduces_debt_once(session):
    representative = Location(name="Представитель касса идемпотентность", kind=LocationKind.REPRESENTATIVE)
    product = Product(
        sku="IDEMP-002",
        name="Товар касса",
        unit_name="шт",
        retail_price=Decimal("100.00"),
        wholesale_price=Decimal("80.00"),
    )
    session.add_all([representative, product])
    await session.flush()
    session.add(InventoryBalance(location_id=representative.id, product_id=product.id, quantity=Decimal("1")))
    await session.commit()
    await create_sale(
        session,
        representative_location_id=representative.id,
        items=[MovementItemIn(product_id=product.id, quantity=Decimal("1"))],
        price_type=PriceType.RETAIL,
        comment="Продажа перед сдачей",
    )

    params = dict(
        representative_location_id=representative.id,
        amount=Decimal("50.00"),
        comment="Сдача из офлайн-очереди",
        client_operation_key="android:cash:00000001",
        client_payload_hash="c" * 64,
    )
    first = await create_cash_handover(session, **params)
    second = await create_cash_handover(session, **params)

    assert first.id == second.id
    assert await representative_debt(session, representative.id) == Decimal("50.00")
    assert await session.scalar(select(func.count(MoneyTransaction.id)).where(MoneyTransaction.kind == MoneyTransactionKind.CASH_HANDOVER)) == 1
