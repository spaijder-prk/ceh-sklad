from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.document_service import cancel_document, document_journal
from app.models import DocumentStatus, Product, Representative, Warehouse
from app.schemas import IssueRequest, QuantityLine, ReceiptRequest, SaleLine, SaleRequest
from app.services import (
    ConflictError,
    issue_to_representative,
    receive_goods,
    register_sale,
    representative_balances,
    representative_debt,
    warehouse_balances,
)


def test_sale_and_issue_can_be_cancelled_without_deleting_history():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="DOC", name="Склад документов")
        representative = Representative(code="REP-DOC", name="Представитель документов")
        product = Product(
            sku="P-DOC",
            name="Товар документов",
            unit="шт",
            retail_price=Decimal("100.00"),
            wholesale_price=Decimal("80.00"),
        )
        session.add_all([warehouse, representative, product])
        session.commit()

        receipt = receive_goods(
            session,
            ReceiptRequest(
                warehouse_id=warehouse.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("10"))],
                external_id="doc-receipt",
            ),
        )
        issue = issue_to_representative(
            session,
            IssueRequest(
                warehouse_id=warehouse.id,
                representative_id=representative.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("4"))],
                external_id="doc-issue",
            ),
        )
        sale = register_sale(
            session,
            SaleRequest(
                representative_id=representative.id,
                lines=[SaleLine(product_id=product.id, quantity=Decimal("2"))],
                external_id="doc-sale",
            ),
        )

        assert representative_debt(session, representative.id).debt == Decimal("200.00")
        assert representative_balances(session, representative.id)[0].quantity == Decimal("2.000")

        sale_cancel = cancel_document(session, sale.document_id)
        assert sale_cancel.status == DocumentStatus.CANCELLED
        assert sale_cancel.stock_changed is True
        assert sale_cancel.debt_changed is True
        assert representative_debt(session, representative.id).debt == Decimal("0.00")
        assert representative_balances(session, representative.id)[0].quantity == Decimal("4.000")

        repeated = cancel_document(session, sale.document_id)
        assert repeated.stock_changed is False
        assert repeated.debt_changed is False
        assert representative_debt(session, representative.id).debt == Decimal("0.00")

        cancel_document(session, issue.document_id)
        assert representative_balances(session, representative.id) == []
        assert warehouse_balances(session, warehouse.id)[0].quantity == Decimal("10.000")

        cancel_document(session, receipt.document_id)
        assert warehouse_balances(session, warehouse.id) == []

        journal = document_journal(session)
        rows = {row.id: row for row in journal}
        assert rows[sale.document_id].status == DocumentStatus.CANCELLED
        assert rows[sale.document_id].sale_amount == Decimal("200.00")
        assert len(rows[sale.document_id].lines) == 1
        assert rows[issue.document_id].status == DocumentStatus.CANCELLED
        assert rows[receipt.document_id].status == DocumentStatus.CANCELLED


def test_receipt_cannot_be_cancelled_when_goods_were_already_used():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="LOCK", name="Склад проверки")
        representative = Representative(code="REP-LOCK", name="Представитель проверки")
        product = Product(
            sku="P-LOCK",
            name="Товар проверки",
            unit="шт",
            retail_price=Decimal("10.00"),
            wholesale_price=Decimal("8.00"),
        )
        session.add_all([warehouse, representative, product])
        session.commit()

        receipt = receive_goods(
            session,
            ReceiptRequest(
                warehouse_id=warehouse.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("10"))],
            ),
        )
        issue_to_representative(
            session,
            IssueRequest(
                warehouse_id=warehouse.id,
                representative_id=representative.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("4"))],
            ),
        )

        with pytest.raises(ConflictError):
            cancel_document(session, receipt.document_id)

        session.rollback()
        assert warehouse_balances(session, warehouse.id)[0].quantity == Decimal("6.000")
        assert representative_balances(session, representative.id)[0].quantity == Decimal("4.000")
