from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Product, Representative, Warehouse
from app.schemas import IssueRequest, QuantityLine, ReceiptRequest
from app.services import ConflictError, issue_to_representative, receive_goods, warehouse_balances


def make_session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def test_cannot_issue_more_than_available():
    with make_session() as session:
        warehouse = Warehouse(code="W1", name="Склад")
        representative = Representative(code="R1", name="Представитель")
        product = Product(
            sku="SKU-1",
            name="Товар",
            retail_price=Decimal("10.00"),
            wholesale_price=Decimal("8.00"),
        )
        session.add_all([warehouse, representative, product])
        session.commit()

        receive_goods(
            session,
            ReceiptRequest(
                warehouse_id=warehouse.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("3"))],
            ),
        )

        with pytest.raises(ConflictError):
            issue_to_representative(
                session,
                IssueRequest(
                    warehouse_id=warehouse.id,
                    representative_id=representative.id,
                    lines=[QuantityLine(product_id=product.id, quantity=Decimal("4"))],
                ),
            )


def test_external_id_is_idempotent():
    with make_session() as session:
        warehouse = Warehouse(code="W1", name="Склад")
        product = Product(
            sku="SKU-1",
            name="Товар",
            retail_price=Decimal("10.00"),
            wholesale_price=Decimal("8.00"),
        )
        session.add_all([warehouse, product])
        session.commit()

        payload = ReceiptRequest(
            warehouse_id=warehouse.id,
            external_id="1c:receipt:100",
            lines=[QuantityLine(product_id=product.id, quantity=Decimal("5"))],
        )
        first = receive_goods(session, payload)
        second = receive_goods(session, payload)

        assert first.document_id == second.document_id
        assert warehouse_balances(session, warehouse.id)[0].quantity == Decimal("5.000")
