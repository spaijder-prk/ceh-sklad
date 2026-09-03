from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionFactory
from app.integration_export import IntegrationExportLink
from app.main import app
from app.models import Location, LocationKind, Product, StockDocument, StockDocumentKind, StockDocumentLine, StockMovement


async def _mixed_adjustment(session) -> StockDocument:
    warehouse = Location(
        name="Склад batch УНФ",
        kind=LocationKind.WAREHOUSE,
        external_1c_id="unf-batch-warehouse",
    )
    plus_product = Product(
        sku="UNF-BATCH-PLUS",
        name="Излишек batch",
        unit_name="шт",
        retail_price=Decimal("10.00"),
        wholesale_price=Decimal("9.00"),
        external_1c_id="unf-batch-plus",
    )
    minus_product = Product(
        sku="UNF-BATCH-MINUS",
        name="Недостача batch",
        unit_name="шт",
        retail_price=Decimal("20.00"),
        wholesale_price=Decimal("18.00"),
        external_1c_id="unf-batch-minus",
    )
    session.add_all([warehouse, plus_product, minus_product])
    await session.flush()

    document = StockDocument(kind=StockDocumentKind.ADJUSTMENT, comment="Смешанная корректировка batch")
    session.add(document)
    await session.flush()
    session.add_all(
        [
            StockDocumentLine(
                document_id=document.id,
                product_id=plus_product.id,
                quantity=Decimal("2.000"),
            ),
            StockDocumentLine(
                document_id=document.id,
                product_id=minus_product.id,
                quantity=Decimal("1.000"),
            ),
            StockMovement(
                document_id=document.id,
                location_id=warehouse.id,
                product_id=plus_product.id,
                quantity_delta=Decimal("2.000"),
            ),
            StockMovement(
                document_id=document.id,
                location_id=warehouse.id,
                product_id=minus_product.id,
                quantity_delta=Decimal("-1.000"),
            ),
        ]
    )
    await session.commit()
    return document


async def test_mixed_adjustment_can_confirm_two_unf_documents_idempotently(monkeypatch, session):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-unf-batch-key")
    document = await _mixed_adjustment(session)
    headers = {"X-1C-Key": "test-unf-batch-key"}
    payload = {
        "entity_type": "stock_document",
        "internal_id": str(document.id),
        "documents": [
            {"external_1c_id": "unf-receipt-100", "external_kind": "Оприходование запасов"},
            {"external_1c_id": "unf-writeoff-101", "external_kind": "Списание запасов"},
        ],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        before = await client.get("/api/v1/integration/1c/unf/outbox", headers=headers)
        confirmed = await client.post("/api/v1/integration/1c/confirm-export-batch", json=payload, headers=headers)
        repeated = await client.post("/api/v1/integration/1c/confirm-export-batch", json=payload, headers=headers)
        after = await client.get("/api/v1/integration/1c/unf/outbox", headers=headers)

    assert before.status_code == 200
    before_row = next(row for row in before.json() if row["internal_id"] == str(document.id))
    assert before_row["requires_split"] is True

    assert confirmed.status_code == 200
    assert confirmed.json()["external_1c_ids"] == ["unf-receipt-100", "unf-writeoff-101"]
    assert confirmed.json()["repeated"] is False
    assert repeated.status_code == 200
    assert repeated.json()["repeated"] is True
    assert all(row["internal_id"] != str(document.id) for row in after.json())

    async with SessionFactory() as check_session:
        saved = await check_session.get(StockDocument, document.id)
        links = list(
            await check_session.scalars(
                select(IntegrationExportLink)
                .where(IntegrationExportLink.entity_internal_id == document.id)
                .order_by(IntegrationExportLink.external_1c_id)
            )
        )
        assert saved is not None
        assert saved.synced_1c_at is not None
        assert saved.external_1c_id is None
        assert [(row.external_1c_id, row.external_kind) for row in links] == [
            ("unf-receipt-100", "Оприходование запасов"),
            ("unf-writeoff-101", "Списание запасов"),
        ]


async def test_batch_confirm_rejects_different_set_after_success(monkeypatch, session):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-unf-batch-key")
    document = await _mixed_adjustment(session)
    headers = {"X-1C-Key": "test-unf-batch-key"}
    payload = {
        "entity_type": "stock_document",
        "internal_id": str(document.id),
        "documents": [
            {"external_1c_id": "unf-receipt-stable", "external_kind": "Оприходование запасов"},
            {"external_1c_id": "unf-writeoff-stable", "external_kind": "Списание запасов"},
        ],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/v1/integration/1c/confirm-export-batch", json=payload, headers=headers)
        changed = await client.post(
            "/api/v1/integration/1c/confirm-export-batch",
            json={
                **payload,
                "documents": [
                    {"external_1c_id": "unf-receipt-stable", "external_kind": "Оприходование запасов"},
                    {"external_1c_id": "unf-writeoff-other", "external_kind": "Списание запасов"},
                ],
            },
            headers=headers,
        )

    assert first.status_code == 200
    assert changed.status_code == 409
    assert "другим набором" in changed.json()["detail"]

    async with SessionFactory() as check_session:
        count = await check_session.scalar(
            select(func.count(IntegrationExportLink.id)).where(
                IntegrationExportLink.entity_internal_id == document.id
            )
        )
        assert count == 2


async def test_multiple_confirmations_are_rejected_for_non_adjustment(monkeypatch, session):
    monkeypatch.setattr(settings, "integration_1c_api_key", "test-unf-batch-key")
    document = StockDocument(kind=StockDocumentKind.TRANSFER, comment="Обычное перемещение")
    session.add(document)
    await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/integration/1c/confirm-export-batch",
            json={
                "entity_type": "stock_document",
                "internal_id": str(document.id),
                "documents": [
                    {"external_1c_id": "unf-transfer-a", "external_kind": "Перемещение запасов"},
                    {"external_1c_id": "unf-transfer-b", "external_kind": "Перемещение запасов"},
                ],
            },
            headers={"X-1C-Key": "test-unf-batch-key"},
        )

    assert response.status_code == 422
    assert "только для корректировки" in response.json()["detail"]
