from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
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
    representative_balances,
    representative_debt,
    warehouse_balances,
)


def test_accounting_flow():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="MAIN", name="Основной")
        representative = Representative(code="REP-1", name="Представитель")
        product = Product(
            sku="P-001",
            name="Товар",
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
        sale_result = register_sale(
            session,
            SaleRequest(
                representative_id=representative.id,
                lines=[SaleLine(product_id=product.id, quantity=Decimal("2"))],
            ),
        )
        register_payment(
            session,
            PaymentRequest(representative_id=representative.id, amount=Decimal("50.00")),
        )

        assert warehouse_balances(session, warehouse.id)[0].quantity == Decimal("6.000")
        assert representative_balances(session, representative.id)[0].quantity == Decimal("2.000")
        assert sale_result.debt_delta == Decimal("200.00")
        assert representative_debt(session, representative.id).debt == Decimal("150.00")


def test_fractional_sale_rounds_money_half_up():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="ROUND", name="Склад округления")
        representative = Representative(code="REP-R", name="Представитель округления")
        product = Product(
            sku="P-ROUND",
            name="Весовой товар",
            unit="кг",
            retail_price=Decimal("3.35"),
            wholesale_price=Decimal("3.35"),
        )
        session.add_all([warehouse, representative, product])
        session.commit()

        receive_goods(
            session,
            ReceiptRequest(
                warehouse_id=warehouse.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("1.000"))],
            ),
        )
        issue_to_representative(
            session,
            IssueRequest(
                warehouse_id=warehouse.id,
                representative_id=representative.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("1.000"))],
            ),
        )

        sale_result = register_sale(
            session,
            SaleRequest(
                representative_id=representative.id,
                lines=[SaleLine(product_id=product.id, quantity=Decimal("0.300"))],
            ),
        )

        assert sale_result.debt_delta == Decimal("1.01")
        assert representative_debt(session, representative.id).debt == Decimal("1.01")


def test_zero_value_sale_moves_stock_without_debt():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="FREE", name="Склад бесплатного товара")
        representative = Representative(code="REP-F", name="Представитель бесплатного товара")
        product = Product(
            sku="P-FREE",
            name="Пробник",
            unit="шт",
            retail_price=Decimal("0.00"),
            wholesale_price=Decimal("0.00"),
        )
        session.add_all([warehouse, representative, product])
        session.commit()

        receive_goods(
            session,
            ReceiptRequest(
                warehouse_id=warehouse.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("1"))],
            ),
        )
        issue_to_representative(
            session,
            IssueRequest(
                warehouse_id=warehouse.id,
                representative_id=representative.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("1"))],
            ),
        )

        sale_result = register_sale(
            session,
            SaleRequest(
                representative_id=representative.id,
                external_id="free-sale-1",
                lines=[SaleLine(product_id=product.id, quantity=Decimal("1"))],
            ),
        )
        repeated_result = register_sale(
            session,
            SaleRequest(
                representative_id=representative.id,
                external_id="free-sale-1",
                lines=[SaleLine(product_id=product.id, quantity=Decimal("1"))],
            ),
        )

        assert sale_result.document_id == repeated_result.document_id
        assert sale_result.debt_delta == Decimal("0.00")
        assert repeated_result.debt_delta == Decimal("0.00")
        assert representative_balances(session, representative.id) == []
        assert representative_debt(session, representative.id).debt == Decimal("0.00")
