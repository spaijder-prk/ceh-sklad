from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.document_service import cancel_document
from app.models import Product, Representative, Warehouse
from app.report_service import report_summary, representative_report
from app.schemas import (
    IssueRequest,
    PaymentRequest,
    QuantityLine,
    ReceiptRequest,
    SaleLine,
    SaleRequest,
)
from app.services import issue_to_representative, receive_goods, register_payment, register_sale


def test_management_reports_exclude_cancelled_sales_and_show_current_state():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="REPORT", name="Отчетный склад")
        first_rep = Representative(code="REP-A", name="Алексей")
        second_rep = Representative(code="REP-B", name="Борис")
        product = Product(
            sku="REPORT-1",
            name="Отчетный товар",
            unit="шт",
            retail_price=Decimal("100.00"),
            wholesale_price=Decimal("80.00"),
        )
        session.add_all([warehouse, first_rep, second_rep, product])
        session.commit()

        receive_goods(
            session,
            ReceiptRequest(
                warehouse_id=warehouse.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("20"))],
            ),
        )
        for representative in (first_rep, second_rep):
            issue_to_representative(
                session,
                IssueRequest(
                    warehouse_id=warehouse.id,
                    representative_id=representative.id,
                    lines=[QuantityLine(product_id=product.id, quantity=Decimal("5"))],
                ),
            )

        register_sale(
            session,
            SaleRequest(
                representative_id=first_rep.id,
                lines=[SaleLine(product_id=product.id, quantity=Decimal("2"))],
            ),
        )
        cancelled_sale = register_sale(
            session,
            SaleRequest(
                representative_id=second_rep.id,
                lines=[SaleLine(product_id=product.id, quantity=Decimal("1"))],
            ),
        )
        cancel_document(session, cancelled_sale.document_id)
        register_payment(
            session,
            PaymentRequest(representative_id=first_rep.id, amount=Decimal("50.00")),
        )

        summary = report_summary(session)
        assert summary.sales_amount == Decimal("200.00")
        assert summary.sales_documents == 1
        assert summary.payments_amount == Decimal("50.00")
        assert summary.current_debt == Decimal("150.00")
        assert summary.warehouse_retail_value == Decimal("1000.00")
        assert summary.representative_stock_retail_value == Decimal("800.00")

        rows = {row.representative_id: row for row in representative_report(session)}
        assert rows[first_rep.id].sales_amount == Decimal("200.00")
        assert rows[first_rep.id].sales_documents == 1
        assert rows[first_rep.id].payments_amount == Decimal("50.00")
        assert rows[first_rep.id].current_debt == Decimal("150.00")
        assert rows[first_rep.id].stock_positions == 1
        assert rows[first_rep.id].stock_retail_value == Decimal("300.00")

        assert rows[second_rep.id].sales_amount == Decimal("0.00")
        assert rows[second_rep.id].sales_documents == 0
        assert rows[second_rep.id].payments_amount == Decimal("0.00")
        assert rows[second_rep.id].current_debt == Decimal("0.00")
        assert rows[second_rep.id].stock_retail_value == Decimal("500.00")


def test_report_period_rejects_reversed_dates():
    from datetime import date

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        with pytest.raises(ValueError):
            report_summary(session, date(2026, 9, 5), date(2026, 9, 4))
