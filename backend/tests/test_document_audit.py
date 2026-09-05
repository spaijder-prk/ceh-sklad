from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.document_service import document_journal
from app.models import Product, StockDocument, User, UserRole, Warehouse
from app.schemas import QuantityLine, ReceiptRequest
from app.security import create_access_token, get_current_user
from app.services import receive_goods


def test_authenticated_operation_records_document_creator():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        user = User(
            email="audit-admin@example.local",
            password_hash="test",
            full_name="Аудитор",
            role=UserRole.ADMIN,
        )
        warehouse = Warehouse(code="AUDIT", name="Склад аудита")
        product = Product(
            sku="AUDIT-1",
            name="Товар аудита",
            unit="шт",
            retail_price=Decimal("10.00"),
            wholesale_price=Decimal("8.00"),
        )
        session.add_all([user, warehouse, product])
        session.commit()

        token = create_access_token(user)
        assert get_current_user(token, session).id == user.id

        result = receive_goods(
            session,
            ReceiptRequest(
                warehouse_id=warehouse.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("2"))],
                external_id="audit-receipt",
            ),
        )

        document = session.get(StockDocument, result.document_id)
        assert document is not None
        assert document.created_by_user_id == user.id

        journal_row = next(row for row in document_journal(session) if row.id == document.id)
        assert journal_row.created_by_user_id == user.id
        assert journal_row.created_by_name == "Аудитор"


def test_system_operation_keeps_creator_empty_without_authenticated_user():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="SYSTEM", name="Системный склад")
        product = Product(
            sku="SYSTEM-1",
            name="Системный товар",
            unit="шт",
            retail_price=Decimal("10.00"),
            wholesale_price=Decimal("8.00"),
        )
        session.add_all([warehouse, product])
        session.commit()

        result = receive_goods(
            session,
            ReceiptRequest(
                warehouse_id=warehouse.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("1"))],
                external_id="system-receipt",
            ),
        )
        document = session.get(StockDocument, result.document_id)
        assert document is not None
        assert document.created_by_user_id is None
