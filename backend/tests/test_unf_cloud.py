from decimal import Decimal

from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import SessionFactory
from app.main import app
from app.models import (
    Location,
    LocationKind,
    MoneyTransaction,
    MoneyTransactionKind,
    Product,
    StockDocument,
    StockDocumentKind,
    StockDocumentLine,
    StockMovement,
)


async def test_unf_profile_describes_cloud_contract(monkeypatch):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-unf-key")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/integration/1c/unf/profile",
            headers={"X-1C-Key": "test-unf-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["target_configuration"] == "1С:Управление нашей фирмой"
    assert body["deployment"] == "cloud"
    assert body["recommended_transport"] == "external_bridge"
    assert body["mappings"]["sale"] == "Расходная накладная"
    assert body["mappings"]["cash_handover"] == "Поступление в кассу"


async def test_unf_outbox_maps_issue_and_cash_handover(monkeypatch):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-unf-key")
    async with SessionFactory() as session:
        warehouse = Location(
            name="Основной склад УНФ",
            kind=LocationKind.WAREHOUSE,
            external_1c_id="unf-warehouse-main",
        )
        representative = Location(
            name="Склад представителя УНФ",
            kind=LocationKind.REPRESENTATIVE,
            external_1c_id="unf-warehouse-rep-1",
        )
        product = Product(
            sku="UNF-001",
            name="Товар УНФ",
            unit_name="шт",
            retail_price=Decimal("100.00"),
            wholesale_price=Decimal("90.00"),
            external_1c_id="unf-product-1",
        )
        session.add_all([warehouse, representative, product])
        await session.flush()

        issue = StockDocument(
            kind=StockDocumentKind.ISSUE_TO_REPRESENTATIVE,
            source_location_id=warehouse.id,
            destination_location_id=representative.id,
            comment="Выдача для УНФ",
        )
        session.add(issue)
        await session.flush()
        session.add(
            StockDocumentLine(
                document_id=issue.id,
                product_id=product.id,
                quantity=Decimal("3.000"),
            )
        )
        session.add(
            MoneyTransaction(
                representative_location_id=representative.id,
                kind=MoneyTransactionKind.CASH_HANDOVER,
                amount=Decimal("-500.00"),
                comment="Сдача выручки для УНФ",
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
    rows = response.json()
    issue_row = next(row for row in rows if row["kind"] == "issue_to_representative")
    cash_row = next(row for row in rows if row["kind"] == "cash_handover")
    assert issue_row["unf_document"] == "Перемещение запасов"
    assert issue_row["ready_for_unf"] is True
    assert issue_row["destination_location_external_1c_id"] == "unf-warehouse-rep-1"
    assert cash_row["unf_document"] == "Поступление в кассу"
    assert cash_row["amount"] == "500.00"
    assert cash_row["ready_for_unf"] is True


async def test_unf_outbox_splits_mixed_adjustment(monkeypatch):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-unf-key")
    async with SessionFactory() as session:
        warehouse = Location(
            name="Склад инвентаризации УНФ",
            kind=LocationKind.WAREHOUSE,
            external_1c_id="unf-inventory-warehouse",
        )
        plus_product = Product(
            sku="UNF-PLUS",
            name="Излишек УНФ",
            unit_name="шт",
            retail_price=Decimal("10.00"),
            wholesale_price=Decimal("9.00"),
            external_1c_id="unf-plus",
        )
        minus_product = Product(
            sku="UNF-MINUS",
            name="Недостача УНФ",
            unit_name="шт",
            retail_price=Decimal("20.00"),
            wholesale_price=Decimal("18.00"),
            external_1c_id="unf-minus",
        )
        session.add_all([warehouse, plus_product, minus_product])
        await session.flush()

        adjustment = StockDocument(
            kind=StockDocumentKind.ADJUSTMENT,
            comment="Смешанная инвентаризация",
        )
        session.add(adjustment)
        await session.flush()
        session.add_all(
            [
                StockDocumentLine(
                    document_id=adjustment.id,
                    product_id=plus_product.id,
                    quantity=Decimal("2.000"),
                ),
                StockDocumentLine(
                    document_id=adjustment.id,
                    product_id=minus_product.id,
                    quantity=Decimal("1.000"),
                ),
                StockMovement(
                    document_id=adjustment.id,
                    location_id=warehouse.id,
                    product_id=plus_product.id,
                    quantity_delta=Decimal("2.000"),
                ),
                StockMovement(
                    document_id=adjustment.id,
                    location_id=warehouse.id,
                    product_id=minus_product.id,
                    quantity_delta=Decimal("-1.000"),
                ),
            ]
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/integration/1c/unf/outbox",
            headers={"X-1C-Key": "test-unf-key"},
        )

    assert response.status_code == 200
    row = next(item for item in response.json() if item["kind"] == "adjustment")
    assert row["requires_split"] is True
    assert row["unf_document"] == "Оприходование запасов + Списание запасов"
    assert row["adjustment_location_external_1c_id"] == "unf-inventory-warehouse"
    deltas = {line["sku"]: line["quantity_delta"] for line in row["lines"]}
    assert deltas == {"UNF-MINUS": "-1.000", "UNF-PLUS": "2.000"}
