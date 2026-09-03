from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionFactory
from app.main import app
from app.models import (
    IntegrationExchangeLog,
    InventoryBalance,
    Location,
    LocationKind,
    Product,
    StockDocument,
    StockMovement,
)
from app.schemas import MovementItemIn, PriceType
from app.services import create_sale


async def test_product_import_is_idempotent(monkeypatch):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-1c-key")
    transport = ASGITransport(app=app)
    payload = {
        "operation_key": "product-import-0001",
        "external_1c_id": "1c-product-001",
        "sku": "SKU-1C-001",
        "name": "Товар из 1С",
        "unit_name": "шт",
        "retail_price": "125.00",
        "wholesale_price": "100.00",
        "is_active": True,
    }
    headers = {"X-1C-Key": "test-1c-key"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/v1/integration/1c/products", json=payload, headers=headers)
        second = await client.post("/api/v1/integration/1c/products", json=payload, headers=headers)
        changed = await client.post(
            "/api/v1/integration/1c/products",
            json={**payload, "name": "Другое содержимое"},
            headers=headers,
        )

    assert first.status_code == 200
    assert first.json()["repeated"] is False
    assert second.status_code == 200
    assert second.json()["repeated"] is True
    assert changed.status_code == 409

    async with SessionFactory() as session:
        assert await session.scalar(select(func.count(Product.id))) == 1
        assert await session.scalar(select(func.count(IntegrationExchangeLog.id))) == 1


async def test_integration_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(settings, "integration_1c_api_key", "correct-key")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/integration/1c/outbox", headers={"X-1C-Key": "wrong-key"})
    assert response.status_code == 401


async def test_stock_adjustment_external_id_never_creates_second_movement(monkeypatch):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-1c-key")
    headers = {"X-1C-Key": "test-1c-key"}
    transport = ASGITransport(app=app)

    product = {
        "operation_key": "product-import-adjustment-01",
        "external_1c_id": "1c-product-adjustment",
        "sku": "SKU-ADJ-1",
        "name": "Товар для инвентаризации",
        "unit_name": "шт",
        "retail_price": "100.00",
        "wholesale_price": "90.00",
        "is_active": True,
    }
    location = {
        "operation_key": "location-import-adjustment-01",
        "external_1c_id": "1c-warehouse-adjustment",
        "name": "Склад инвентаризации",
        "kind": "warehouse",
    }
    adjustment = {
        "operation_key": "adjustment-import-0001",
        "external_1c_id": "1c-inventory-document-001",
        "location_external_1c_id": "1c-warehouse-adjustment",
        "comment": "Контрольная инвентаризация",
        "items": [{"product_external_1c_id": "1c-product-adjustment", "quantity_delta": "5.000"}],
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/v1/integration/1c/products", json=product, headers=headers)).status_code == 200
        assert (await client.post("/api/v1/integration/1c/locations", json=location, headers=headers)).status_code == 200
        first = await client.post("/api/v1/integration/1c/stock-adjustments", json=adjustment, headers=headers)
        same_request = await client.post("/api/v1/integration/1c/stock-adjustments", json=adjustment, headers=headers)
        same_document_new_key = await client.post(
            "/api/v1/integration/1c/stock-adjustments",
            json={**adjustment, "operation_key": "adjustment-import-0002"},
            headers=headers,
        )

    assert first.status_code == 200 and first.json()["repeated"] is False
    assert same_request.status_code == 200 and same_request.json()["repeated"] is True
    assert same_document_new_key.status_code == 200 and same_document_new_key.json()["repeated"] is True

    async with SessionFactory() as session:
        balance = await session.scalar(select(InventoryBalance))
        document_count = await session.scalar(
            select(func.count(StockDocument.id)).where(StockDocument.external_1c_id == "1c-inventory-document-001")
        )
        movement_count = await session.scalar(select(func.count(StockMovement.id)))
        assert balance is not None and balance.quantity == Decimal("5.000")
        assert document_count == 1
        assert movement_count == 1


async def test_outbox_confirmation_is_idempotent_and_removes_exported_document(monkeypatch, session):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-1c-key")
    headers = {"X-1C-Key": "test-1c-key"}

    representative = Location(
        name="Представитель для outbox",
        kind=LocationKind.REPRESENTATIVE,
        external_1c_id="1c-representative-outbox",
    )
    product = Product(
        sku="OUTBOX-1",
        name="Товар outbox",
        unit_name="шт",
        retail_price=Decimal("150.00"),
        wholesale_price=Decimal("120.00"),
        external_1c_id="1c-product-outbox",
    )
    session.add_all([representative, product])
    await session.flush()
    session.add(InventoryBalance(location_id=representative.id, product_id=product.id, quantity=Decimal("3")))
    await session.commit()

    document = await create_sale(
        session,
        representative_location_id=representative.id,
        items=[MovementItemIn(product_id=product.id, quantity=Decimal("1"))],
        price_type=PriceType.RETAIL,
        comment="Продажа для проверки outbox",
    )

    transport = ASGITransport(app=app)
    confirm_payload = {
        "entity_type": "stock_document",
        "internal_id": str(document.id),
        "external_1c_id": "1c-sale-confirmed-001",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        before = await client.get("/api/v1/integration/1c/outbox", headers=headers)
        first = await client.post("/api/v1/integration/1c/confirm-export", json=confirm_payload, headers=headers)
        repeated = await client.post("/api/v1/integration/1c/confirm-export", json=confirm_payload, headers=headers)
        conflict = await client.post(
            "/api/v1/integration/1c/confirm-export",
            json={**confirm_payload, "external_1c_id": "another-1c-id"},
            headers=headers,
        )
        after = await client.get("/api/v1/integration/1c/outbox", headers=headers)

    assert before.status_code == 200
    assert any(row["internal_id"] == str(document.id) for row in before.json())
    assert first.status_code == 200 and first.json()["repeated"] is False
    assert repeated.status_code == 200 and repeated.json()["repeated"] is True
    assert conflict.status_code == 409
    assert after.status_code == 200
    assert all(row["internal_id"] != str(document.id) for row in after.json())

    async with SessionFactory() as check_session:
        saved = await check_session.get(StockDocument, document.id)
        outbound_logs = await check_session.scalar(
            select(func.count(IntegrationExchangeLog.id)).where(IntegrationExchangeLog.direction == "outbound")
        )
        assert saved is not None and saved.external_1c_id == "1c-sale-confirmed-001" and saved.synced_1c_at is not None
        assert outbound_logs == 1


async def test_1c_cannot_archive_product_with_stock(monkeypatch):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-1c-key")
    headers = {"X-1C-Key": "test-1c-key"}
    transport = ASGITransport(app=app)
    product = {
        "operation_key": "safe-archive-product-create",
        "external_1c_id": "1c-safe-archive-product",
        "sku": "SAFE-ARCHIVE-1",
        "name": "Товар с остатком",
        "unit_name": "шт",
        "retail_price": "100.00",
        "wholesale_price": "90.00",
        "is_active": True,
    }
    location = {
        "operation_key": "safe-archive-location-create",
        "external_1c_id": "1c-safe-archive-location",
        "name": "Склад безопасной архивации",
        "kind": "warehouse",
    }
    adjustment = {
        "operation_key": "safe-archive-adjustment",
        "external_1c_id": "1c-safe-archive-document",
        "location_external_1c_id": location["external_1c_id"],
        "comment": "Создание остатка для проверки архивации",
        "items": [{"product_external_1c_id": product["external_1c_id"], "quantity_delta": "2.000"}],
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/v1/integration/1c/products", json=product, headers=headers)).status_code == 200
        assert (await client.post("/api/v1/integration/1c/locations", json=location, headers=headers)).status_code == 200
        assert (await client.post("/api/v1/integration/1c/stock-adjustments", json=adjustment, headers=headers)).status_code == 200
        archived = await client.post(
            "/api/v1/integration/1c/products",
            json={**product, "operation_key": "safe-archive-product-disable", "is_active": False},
            headers=headers,
        )

    assert archived.status_code == 409
    assert "ненулевым остатком" in archived.json()["detail"]

    async with SessionFactory() as session:
        saved = await session.scalar(select(Product).where(Product.external_1c_id == product["external_1c_id"]))
        failed = await session.scalar(
            select(IntegrationExchangeLog).where(IntegrationExchangeLog.operation_key == "safe-archive-product-disable")
        )
        assert saved is not None and saved.is_active is True
        assert failed is not None and failed.status == "failed"


async def test_1c_adjustment_rejects_archived_product_and_location(monkeypatch, session):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-1c-key")
    headers = {"X-1C-Key": "test-1c-key"}
    archived_product = Product(
        sku="ARCHIVED-1C-PRODUCT",
        name="Архивный товар 1С",
        unit_name="шт",
        retail_price=Decimal("10.00"),
        wholesale_price=Decimal("9.00"),
        external_1c_id="1c-archived-product",
        is_active=False,
    )
    active_product = Product(
        sku="ACTIVE-1C-PRODUCT",
        name="Активный товар 1С",
        unit_name="шт",
        retail_price=Decimal("10.00"),
        wholesale_price=Decimal("9.00"),
        external_1c_id="1c-active-product",
        is_active=True,
    )
    active_location = Location(
        name="Активный склад 1С",
        kind=LocationKind.WAREHOUSE,
        external_1c_id="1c-active-location",
        is_active=True,
    )
    archived_location = Location(
        name="Архивный склад 1С",
        kind=LocationKind.WAREHOUSE,
        external_1c_id="1c-archived-location",
        is_active=False,
    )
    session.add_all([archived_product, active_product, active_location, archived_location])
    await session.commit()

    transport = ASGITransport(app=app)
    archived_product_adjustment = {
        "operation_key": "archived-product-adjustment",
        "external_1c_id": "1c-archived-product-document",
        "location_external_1c_id": "1c-active-location",
        "comment": "Попытка изменить архивный товар",
        "items": [{"product_external_1c_id": "1c-archived-product", "quantity_delta": "1.000"}],
    }
    archived_location_adjustment = {
        "operation_key": "archived-location-adjustment",
        "external_1c_id": "1c-archived-location-document",
        "location_external_1c_id": "1c-archived-location",
        "comment": "Попытка изменить архивный склад",
        "items": [{"product_external_1c_id": "1c-active-product", "quantity_delta": "1.000"}],
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        product_response = await client.post(
            "/api/v1/integration/1c/stock-adjustments", json=archived_product_adjustment, headers=headers
        )
        location_response = await client.post(
            "/api/v1/integration/1c/stock-adjustments", json=archived_location_adjustment, headers=headers
        )

    assert product_response.status_code == 409
    assert "архивного товара" in product_response.json()["detail"]
    assert location_response.status_code == 409
    assert "архивного места хранения" in location_response.json()["detail"]

    async with SessionFactory() as check_session:
        assert await check_session.scalar(select(func.count(InventoryBalance.id))) == 0
        failed_count = await check_session.scalar(
            select(func.count(IntegrationExchangeLog.id)).where(IntegrationExchangeLog.status == "failed")
        )
        assert failed_count == 2


async def test_1c_cannot_change_existing_location_kind(monkeypatch):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-1c-key")
    headers = {"X-1C-Key": "test-1c-key"}
    transport = ASGITransport(app=app)
    location = {
        "operation_key": "location-kind-create",
        "external_1c_id": "1c-location-kind",
        "name": "Склад с постоянным типом",
        "kind": "warehouse",
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/v1/integration/1c/locations", json=location, headers=headers)
        changed = await client.post(
            "/api/v1/integration/1c/locations",
            json={**location, "operation_key": "location-kind-change", "kind": "representative"},
            headers=headers,
        )

    assert created.status_code == 200
    assert changed.status_code == 409
    assert "Тип существующего места хранения" in changed.json()["detail"]

    async with SessionFactory() as session:
        saved = await session.scalar(select(Location).where(Location.external_1c_id == location["external_1c_id"]))
        assert saved is not None and saved.kind == LocationKind.WAREHOUSE
