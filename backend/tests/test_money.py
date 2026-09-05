from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import MoneyOperation, Product, Representative, Warehouse
from app.money_service import money_journal, reverse_payment
from app.schemas import (
    IssueRequest,
    PaymentRequest,
    QuantityLine,
    ReceiptRequest,
    SaleLine,
    SaleRequest,
)
from app.services import (
    ConflictError,
    issue_to_representative,
    receive_goods,
    register_payment,
    register_sale,
    representative_debt,
)


def test_payment_reversal_restores_debt_and_is_idempotent():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="MONEY", name="Денежный склад")
        representative = Representative(code="REP-M", name="Денежный представитель")
        product = Product(
            sku="MONEY-1",
            name="Денежный товар",
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
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("5"))],
            ),
        )
        issue_to_representative(
            session,
            IssueRequest(
                warehouse_id=warehouse.id,
                representative_id=representative.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("2"))],
            ),
        )
        sale = register_sale(
            session,
            SaleRequest(
                representative_id=representative.id,
                lines=[SaleLine(product_id=product.id, quantity=Decimal("2"))],
            ),
        )
        payment = register_payment(
            session,
            PaymentRequest(
                representative_id=representative.id,
                amount=Decimal("50.00"),
                external_id="payment-to-reverse",
            ),
        )
        assert representative_debt(session, representative.id).debt == Decimal("150.00")

        result = reverse_payment(session, payment.money_posting_id)
        assert result.debt_delta == Decimal("50.00")
        assert result.already_reversed is False
        assert representative_debt(session, representative.id).debt == Decimal("200.00")

        repeated = reverse_payment(session, payment.money_posting_id)
        assert repeated.reversal_id == result.reversal_id
        assert repeated.already_reversed is True
        assert representative_debt(session, representative.id).debt == Decimal("200.00")

        rows = money_journal(session)
        original = next(row for row in rows if row.id == payment.money_posting_id)
        reversal = next(row for row in rows if row.id == result.reversal_id)
        assert original.operation == MoneyOperation.PAYMENT
        assert original.amount == Decimal("-50.00")
        assert original.reversed is True
        assert reversal.operation == MoneyOperation.ADJUSTMENT
        assert reversal.amount == Decimal("50.00")

        sale_posting = next(
            row for row in rows if row.document_id == sale.document_id and row.operation == MoneyOperation.SALE
        )
        with pytest.raises(ConflictError):
            reverse_payment(session, sale_posting.id)
