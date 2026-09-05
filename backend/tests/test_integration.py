from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base
from app.integration_api import require_external_id, require_integration_key
from app.integration_service import build_1c_snapshot
from app.models import Product, Representative, Warehouse
from app.schemas import (
    IssueRequest,
    PaymentRequest,
    QuantityLine,
    ReceiptRequest,
    SaleLine,
    SaleRequest,
)
from app.services import (
    issue_to_representative,
    receive_goods,
    register_payment,
    register_sale,
)


def test_1c_snapshot_contains_current_accounting_state():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="1C-WH", name="Склад 1С")
        representative = Representative(code="1C-REP", name="Представитель 1С")
        product = Product(
            sku="1C-001",
            name="Товар 1С",
            unit="шт",
            retail_price=Decimal("100.00"),
            wholesale_price=Decimal("80.00"),
        )
        session.add_all([warehouse, representative, product])
        session.commit()

        receive_goods(
            session,
            ReceiptRequest(
                warehouse_id=warehouse.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("10"))],
                external_id="1c-receipt-1",
            ),
        )
        issue_to_representative(
            session,
            IssueRequest(
                warehouse_id=warehouse.id,
                representative_id=representative.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("4"))],
                external_id="1c-issue-1",
            ),
        )
        register_sale(
            session,
            SaleRequest(
                representative_id=representative.id,
                lines=[SaleLine(product_id=product.id, quantity=Decimal("1"))],
                external_id="1c-sale-1",
            ),
        )
        register_payment(
            session,
            PaymentRequest(
                representative_id=representative.id,
                amount=Decimal("20.00"),
                external_id="1c-payment-1",
            ),
        )

        snapshot = build_1c_snapshot(session)
        assert len(snapshot.warehouses) == 1
        assert len(snapshot.products) == 1
        assert len(snapshot.representatives) == 1
        assert snapshot.warehouse_balances[0].quantity == Decimal("6.000")
        assert snapshot.representative_balances[0].quantity == Decimal("3.000")
        assert snapshot.debts[0].debt == Decimal("80.00")


def test_1c_operations_require_external_id():
    payload = ReceiptRequest(
        warehouse_id=uuid4(),
        lines=[QuantityLine(product_id=uuid4(), quantity=Decimal("1"))],
    )
    with pytest.raises(HTTPException) as error:
        require_external_id(payload)
    assert error.value.status_code == 422

    payload.external_id = "1c-document-42"
    require_external_id(payload)


def test_1c_integration_key_is_separate_from_user_jwt():
    original = settings.integration_api_key
    settings.integration_api_key = "integration-secret"
    try:
        require_integration_key("integration-secret")
        with pytest.raises(HTTPException) as error:
            require_integration_key("wrong-secret")
        assert error.value.status_code == 401
    finally:
        settings.integration_api_key = original
