from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.database import SessionFactory
from app.main import app
from app.models import AuditLog


async def test_integration_mutation_is_audited_without_request_body(monkeypatch):
    monkeypatch.setattr(settings, "integration_1c_api_key", "audit-test-key")
    transport = ASGITransport(app=app)
    payload = {
        "operation_key": "audit-product-0001",
        "external_1c_id": "audit-product",
        "sku": "AUDIT-1",
        "name": "Товар для аудита",
        "unit_name": "шт",
        "retail_price": "10.00",
        "wholesale_price": "9.00",
        "is_active": True,
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/integration/1c/products",
            json=payload,
            headers={"X-1C-Key": "audit-test-key"},
        )
    assert response.status_code == 200

    async with SessionFactory() as session:
        row = await session.scalar(select(AuditLog))
        assert row is not None
        assert row.actor_type == "1c"
        assert row.method == "POST"
        assert row.path == "/api/v1/integration/1c/products"
        assert row.status_code == 200
        assert not hasattr(row, "payload")
