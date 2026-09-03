from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionFactory
from app.main import app
from app.models import IntegrationExchangeLog, Product


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
