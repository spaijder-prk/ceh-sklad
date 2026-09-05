import asyncio

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionFactory
from app.main import app
from app.models import InventoryBalance, Location, LocationKind, Product, StockDocument
from app.schemas import AdjustmentItemIn
from app.services import create_adjustment


async def test_archive_operation_key_does_not_rearchive_after_reactivation(monkeypatch, session):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-1c-key")
    product = Product(
        sku="ARCHIVE-IDEMPOTENT",
        name="Товар для идемпотентной архивации",
        unit_name="шт",
        retail_price=100,
        wholesale_price=90,
        external_1c_id="unf-archive-idempotent",
        is_active=True,
    )
    session.add(product)
    await session.commit()

    headers = {"X-1C-Key": "test-1c-key"}
    transport = ASGITransport(app=app)
    payload = {"operation_key": "unf-archive-version-0001"}
    path = "/api/v1/integration/1c/products/unf-archive-idempotent/archive"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(path, json=payload, headers=headers)
        repeated = await client.post(path, json=payload, headers=headers)

    assert first.status_code == 200 and first.json()["repeated"] is False
    assert repeated.status_code == 200 and repeated.json()["repeated"] is True

    async with SessionFactory() as reactivate_session:
        saved = await reactivate_session.scalar(
            select(Product).where(Product.external_1c_id == "unf-archive-idempotent")
        )
        assert saved is not None
        saved.is_active = True
        await reactivate_session.commit()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        stale_retry = await client.post(path, json=payload, headers=headers)

    assert stale_retry.status_code == 200 and stale_retry.json()["repeated"] is True
    async with SessionFactory() as check_session:
        saved = await check_session.scalar(
            select(Product).where(Product.external_1c_id == "unf-archive-idempotent")
        )
        assert saved is not None and saved.is_active is True


async def test_stock_change_waits_for_product_guard_and_is_rejected_after_archive(session):
    product = Product(
        sku="ARCHIVE-RACE",
        name="Товар для конкурентной архивации",
        unit_name="шт",
        retail_price=100,
        wholesale_price=90,
        external_1c_id="unf-archive-race",
        is_active=True,
    )
    location = Location(name="Склад race", kind=LocationKind.WAREHOUSE)
    session.add_all([product, location])
    await session.commit()
    product_id = product.id
    location_id = location.id

    archive_session = SessionFactory()
    stock_session = SessionFactory()
    try:
        locked = await archive_session.scalar(
            select(Product).where(Product.id == product_id).with_for_update()
        )
        assert locked is not None

        stock_task = asyncio.create_task(
            create_adjustment(
                stock_session,
                location_id=location_id,
                items=[AdjustmentItemIn(product_id=product_id, quantity_delta=1)],
                comment="Конкурентное движение во время архивации",
                created_by_id=None,
            )
        )
        await asyncio.sleep(0.1)
        assert stock_task.done() is False

        locked.is_active = False
        await archive_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await stock_task
        assert exc_info.value.status_code == 409
        assert "архивирован" in str(exc_info.value.detail)
        await stock_session.rollback()
    finally:
        await archive_session.close()
        await stock_session.close()

    async with SessionFactory() as check_session:
        balance_count = await check_session.scalar(select(func.count(InventoryBalance.id)))
        document_count = await check_session.scalar(select(func.count(StockDocument.id)))
        saved = await check_session.get(Product, product_id)
        assert balance_count == 0
        assert document_count == 0
        assert saved is not None and saved.is_active is False
