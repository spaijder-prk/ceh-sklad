from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.document_service import document_journal
from app.models import Product, Representative, Warehouse
from app.schemas import IssueRequest, QuantityLine, ReceiptRequest, SaleLine, SaleRequest
from app.services import issue_to_representative, receive_goods, register_sale


def test_representative_document_journal_is_scoped_to_own_movements():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="HISTORY", name="Склад истории")
        first_rep = Representative(code="REP-H1", name="Первый")
        second_rep = Representative(code="REP-H2", name="Второй")
        product = Product(
            sku="HISTORY-1",
            name="Товар истории",
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
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("10"))],
            ),
        )
        first_issue = issue_to_representative(
            session,
            IssueRequest(
                warehouse_id=warehouse.id,
                representative_id=first_rep.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("4"))],
            ),
        )
        second_issue = issue_to_representative(
            session,
            IssueRequest(
                warehouse_id=warehouse.id,
                representative_id=second_rep.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("3"))],
            ),
        )
        first_sale = register_sale(
            session,
            SaleRequest(
                representative_id=first_rep.id,
                lines=[SaleLine(product_id=product.id, quantity=Decimal("1"))],
            ),
        )
        second_sale = register_sale(
            session,
            SaleRequest(
                representative_id=second_rep.id,
                lines=[SaleLine(product_id=product.id, quantity=Decimal("1"))],
            ),
        )

        first_rows = document_journal(session, representative_id=first_rep.id)
        first_ids = {row.id for row in first_rows}
        assert first_issue.document_id in first_ids
        assert first_sale.document_id in first_ids
        assert second_issue.document_id not in first_ids
        assert second_sale.document_id not in first_ids
        assert all(
            any(line.representative_id == first_rep.id for line in row.lines)
            for row in first_rows
        )

        second_rows = document_journal(session, representative_id=second_rep.id)
        second_ids = {row.id for row in second_rows}
        assert second_issue.document_id in second_ids
        assert second_sale.document_id in second_ids
        assert first_issue.document_id not in second_ids
        assert first_sale.document_id not in second_ids
