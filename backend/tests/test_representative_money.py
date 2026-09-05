from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Product, Representative, Warehouse
from app.money_service import money_journal
from app.schemas import (
    IssueRequest,
    PaymentRequest,
    QuantityLine,
    ReceiptRequest,
    SaleLine,
    SaleRequest,
)
from app.services import issue_to_representative, receive_goods, register_payment, register_sale


def test_representative_money_journal_is_scoped_to_own_postings():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="MONEY-HISTORY", name="Склад денежных историй")
        first_rep = Representative(code="MREP-1", name="Первый")
        second_rep = Representative(code="MREP-2", name="Второй")
        product = Product(
            sku="MONEY-HISTORY-1",
            name="Товар",
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
        for representative in (first_rep, second_rep):
            issue_to_representative(
                session,
                IssueRequest(
                    warehouse_id=warehouse.id,
                    representative_id=representative.id,
                    lines=[QuantityLine(product_id=product.id, quantity=Decimal("2"))],
                ),
            )
            register_sale(
                session,
                SaleRequest(
                    representative_id=representative.id,
                    lines=[SaleLine(product_id=product.id, quantity=Decimal("1"))],
                ),
            )

        first_payment = register_payment(
            session,
            PaymentRequest(representative_id=first_rep.id, amount=Decimal("25.00")),
        )
        register_payment(
            session,
            PaymentRequest(representative_id=second_rep.id, amount=Decimal("40.00")),
        )

        first_rows = money_journal(session, representative_id=first_rep.id)
        assert len(first_rows) == 2
        assert {row.representative_id for row in first_rows} == {first_rep.id}
        assert {row.operation.value for row in first_rows} == {"sale", "payment"}
        assert any(row.id == first_payment.money_posting_id for row in first_rows)

        second_rows = money_journal(session, representative_id=second_rep.id)
        assert len(second_rows) == 2
        assert {row.representative_id for row in second_rows} == {second_rep.id}
        assert first_payment.money_posting_id not in {row.id for row in second_rows}
