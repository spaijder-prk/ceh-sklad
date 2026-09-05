from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base
from app.document_service import cancel_document
from app.integration_api import require_external_id, require_integration_key
from app.integration_service import (
    build_1c_document_page,
    build_1c_money_posting_page,
    build_1c_snapshot,
    decode_1c_cursor,
    encode_1c_cursor,
)
from app.models import DocumentStatus, Product, Representative, Warehouse
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


def test_1c_cursor_round_trip_and_invalid_value():
    entity_id = uuid4()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="CURSOR", name="Курсор")
        product = Product(
            sku="CURSOR-1",
            name="Товар курсора",
            unit="шт",
            retail_price=Decimal("1.00"),
            wholesale_price=Decimal("1.00"),
        )
        session.add_all([warehouse, product])
        session.commit()
        result = receive_goods(
            session,
            ReceiptRequest(
                warehouse_id=warehouse.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("1"))],
                external_id="cursor-receipt",
            ),
        )
        page = build_1c_document_page(session, cursor=None, limit=10)
        document = next(item for item in page.items if item.id == result.document_id)
        cursor = encode_1c_cursor(document.updated_at, entity_id)
        moment, decoded_id = decode_1c_cursor(cursor)
        assert decoded_id == entity_id
        assert moment.tzinfo is not None

    with pytest.raises(ValueError):
        decode_1c_cursor("!!!")


def test_1c_incremental_documents_repeat_changed_document_after_cancellation():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        warehouse = Warehouse(code="INC-WH", name="Инкрементальный склад")
        representative = Representative(code="INC-REP", name="Инкрементальный представитель")
        product = Product(
            sku="INC-001",
            name="Инкрементальный товар",
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
                external_id="inc-receipt",
            ),
        )
        issue = issue_to_representative(
            session,
            IssueRequest(
                warehouse_id=warehouse.id,
                representative_id=representative.id,
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("1"))],
                external_id="inc-issue",
            ),
        )

        first_page = build_1c_document_page(session, cursor=None, limit=1)
        assert first_page.has_more is True
        assert first_page.next_cursor is not None

        second_page = build_1c_document_page(
            session,
            cursor=first_page.next_cursor,
            limit=10,
        )
        assert second_page.has_more is False
        assert second_page.next_cursor is not None
        initial_ids = {item.id for item in first_page.items + second_page.items}
        assert issue.document_id in initial_ids

        cancel_document(session, issue.document_id)
        changed_page = build_1c_document_page(
            session,
            cursor=second_page.next_cursor,
            limit=10,
        )
        changed = next(item for item in changed_page.items if item.id == issue.document_id)
        assert changed.status == DocumentStatus.CANCELLED
        assert changed_page.next_cursor != second_page.next_cursor


def test_1c_incremental_money_postings_do_not_repeat_previous_page():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        representative = Representative(code="MONEY-REP", name="Денежный представитель")
        session.add(representative)
        session.commit()

        register_payment(
            session,
            PaymentRequest(
                representative_id=representative.id,
                amount=Decimal("10.00"),
                external_id="money-payment-1",
            ),
        )
        register_payment(
            session,
            PaymentRequest(
                representative_id=representative.id,
                amount=Decimal("20.00"),
                external_id="money-payment-2",
            ),
        )

        first_page = build_1c_money_posting_page(session, cursor=None, limit=1)
        assert first_page.has_more is True
        assert first_page.next_cursor is not None

        second_page = build_1c_money_posting_page(
            session,
            cursor=first_page.next_cursor,
            limit=10,
        )
        first_ids = {item.id for item in first_page.items}
        second_ids = {item.id for item in second_page.items}
        assert first_ids.isdisjoint(second_ids)
        assert len(first_ids | second_ids) == 2
