from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


async def test_archive_check_reports_unknown_zero_and_nonzero_stock(monkeypatch):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-1c-key")
    headers = {"X-1C-Key": "test-1c-key"}
    transport = ASGITransport(app=app)
    product = {
        "operation_key": "archive-check-product-create",
        "external_1c_id": "archive-check-product",
        "sku": "ARCHIVE-CHECK-1",
        "name": "Товар для archive-check",
        "unit_name": "шт",
        "retail_price": "100.00",
        "wholesale_price": "90.00",
        "is_active": True,
    }
    location = {
        "operation_key": "archive-check-location-create",
        "external_1c_id": "archive-check-location",
        "name": "Склад archive-check",
        "kind": "warehouse",
    }
    adjustment = {
        "operation_key": "archive-check-adjustment",
        "external_1c_id": "archive-check-adjustment-doc",
        "location_external_1c_id": location["external_1c_id"],
        "comment": "Остаток для проверки archive-check",
        "items": [{"product_external_1c_id": product["external_1c_id"], "quantity_delta": "2.000"}],
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unknown = await client.get(
            "/api/v1/integration/1c/products/not-existing/archive-check",
            headers=headers,
        )
        assert (await client.post("/api/v1/integration/1c/products", json=product, headers=headers)).status_code == 200
        zero = await client.get(
            f"/api/v1/integration/1c/products/{product['external_1c_id']}/archive-check",
            headers=headers,
        )
        assert (await client.post("/api/v1/integration/1c/locations", json=location, headers=headers)).status_code == 200
        assert (await client.post("/api/v1/integration/1c/stock-adjustments", json=adjustment, headers=headers)).status_code == 200
        nonzero = await client.get(
            f"/api/v1/integration/1c/products/{product['external_1c_id']}/archive-check",
            headers=headers,
        )

    assert unknown.status_code == 200
    assert unknown.json()["exists"] is False
    assert unknown.json()["can_archive"] is False

    assert zero.status_code == 200
    assert zero.json()["exists"] is True
    assert zero.json()["is_active"] is True
    assert zero.json()["total_stock"] == "0"
    assert zero.json()["can_archive"] is True

    assert nonzero.status_code == 200
    assert nonzero.json()["total_stock"] == "2.000"
    assert nonzero.json()["can_archive"] is False
    assert "ненулевым остатком" in nonzero.json()["reason"]
