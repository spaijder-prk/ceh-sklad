from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.document_service import cancel_document, document_journal
from app.models import Product, Representative, User, UserRole, Warehouse
from app.money_service import money_journal, reverse_payment
from app.schemas import PaymentRequest, QuantityLine, ReceiptRequest
from app.services import receive_goods, register_payment


def test_document_cancellation_records_actor_and_time():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        creator = User(
            email="creator@example.local",
            password_hash="test",
            full_name="Создатель документа",
            role=UserRole.ADMIN,
        )
        canceller = User(
            email="canceller@example.local",
            password_hash="test",
            full_name="Автор сторно",
            role=UserRole.ADMIN,
        )
        warehouse = Warehouse(code="CANCEL-AUDIT", name="Склад сторно")
        product = Product(
            sku="CANCEL-AUDIT-1",
            name="Товар сторно",
            unit="шт",
            retail_price=Decimal("10.00"),
            wholesale_price=Decimal("8.00"),
        )
        session.add_all([creator, canceller, warehouse, product])
        session.commit()

        session.info["current_user_id"] = creator.id
        result = receive_goods(
            session,
            ReceiptRequest(
                warehouse_id=warehouse.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("2"))],
                external_id="cancel-audit-receipt",
            ),
        )

        session.info["current_user_id"] = canceller.id
        cancel_document(session, result.document_id)
        row = next(item for item in document_journal(session) if item.id == result.document_id)
        assert row.created_by_user_id == creator.id
        assert row.created_by_name == creator.full_name
        assert row.cancelled_by_user_id == canceller.id
        assert row.cancelled_by_name == canceller.full_name
        assert row.cancelled_at is not None


def test_payment_and_reversal_record_different_actors():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        cashier = User(
            email="cashier@example.local",
            password_hash="test",
            full_name="Кассир",
            role=UserRole.ADMIN,
        )
        auditor = User(
            email="auditor@example.local",
            password_hash="test",
            full_name="Проверяющий",
            role=UserRole.ADMIN,
        )
        representative = Representative(code="AUDIT-REP", name="Представитель")
        session.add_all([cashier, auditor, representative])
        session.commit()

        session.info["current_user_id"] = cashier.id
        payment = register_payment(
            session,
            PaymentRequest(
                representative_id=representative.id,
                amount=Decimal("125.50"),
                external_id="audit-payment",
            ),
        )

        session.info["current_user_id"] = auditor.id
        reverse_payment(session, payment.money_posting_id)

        row = next(item for item in money_journal(session) if item.id == payment.money_posting_id)
        assert row.created_by_user_id == cashier.id
        assert row.created_by_name == cashier.full_name
        assert row.reversed is True
        assert row.reversed_by_user_id == auditor.id
        assert row.reversed_by_name == auditor.full_name
        assert row.reversed_at is not None
