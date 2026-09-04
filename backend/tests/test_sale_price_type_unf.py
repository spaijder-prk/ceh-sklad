from decimal import Decimal

from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.models import InventoryBalance, Location, LocationKind, Product, StockDocument, StockDocumentKind, StockDocumentLine
from app.schemas import MovementItemIn, PriceType
from app.services import create_sale


async def test_sale_price_type_is_persisted_and_exported_to_unf(monkeypatch, session):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-unf-key")
    representative = Location(
        name="Представитель с типом цены",
        kind=LocationKind.REPRESENTATIVE,
        external_1c_id="unf-price-representative",
    )
    product = Product(
        sku="UNF-PRICE-1",
        name="Товар с типом цены",
        unit_name="шт",
        retail_price=Decimal("150.00"),
        wholesale_price=Decimal("120.00"),
        external_1c_id="unf-price-product",
    )
    session.add_all([representative, product])
    await session.flush()
    session.add(
        InventoryBalance(
            location_id=representative.id,
            product_id=product.id,
            quantity=Decimal("5.000"),
        )
    )
    await session.commit()

    document = await create_sale(
        session,
        representative_location_id=representative.id,
        items=[MovementItemIn(product_id=product.id, quantity=Decimal("1.000"))],
        price_type=PriceType.WHOLESALE,
        comment="Оптовая продажа для УНФ",
    )
    assert document.sale_price_type == "wholesale"

    legacy = StockDocument(
        kind=StockDocumentKind.SALE,
        source_location_id=representative.id,
        comment="Legacy-продажа без сохраненного типа цены",
    )
    session.add(legacy)
    await session.flush()
    session.add(
        StockDocumentLine(
            document_id=legacy.id,
            product_id=product.id,
            quantity=Decimal("1.000"),
            unit_price=Decimal("150.00"),
        )
    )
    await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/integration/1c/unf/outbox",
            headers={"X-1C-Key": "test-unf-key"},
        )

    assert response.status_code == 200
    by_id = {row["internal_id"]: row for row in response.json()}
    current = by_id[str(document.id)]
    legacy_row = by_id[str(legacy.id)]
    assert current["sale_price_type"] == "wholesale"
    assert current["ready_for_unf"] is True
    assert legacy_row["sale_price_type"] is None
    assert legacy_row["ready_for_unf"] is False
    assert any("legacy-продажу" in reason for reason in legacy_row["blocking_reasons"])
