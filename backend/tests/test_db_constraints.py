from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import InventoryBalance, Location, LocationKind, Product


async def test_database_rejects_negative_product_price(session):
    session.add(
        Product(
            sku="NEG-PRICE",
            name="Товар с ошибочной ценой",
            unit_name="шт",
            retail_price=Decimal("-0.01"),
            wholesale_price=Decimal("10.00"),
        )
    )

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_database_rejects_negative_inventory_balance(session):
    location = Location(name="Склад ограничений", kind=LocationKind.WAREHOUSE)
    product = Product(
        sku="NEG-STOCK",
        name="Товар ограничений",
        unit_name="шт",
        retail_price=Decimal("10.00"),
        wholesale_price=Decimal("9.00"),
    )
    session.add_all([location, product])
    await session.flush()
    session.add(
        InventoryBalance(
            location_id=location.id,
            product_id=product.id,
            quantity=Decimal("-0.001"),
        )
    )

    with pytest.raises(IntegrityError):
        await session.flush()
