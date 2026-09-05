from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import (
    DocumentStatus,
    DocumentType,
    MoneyPosting,
    Product,
    Representative,
    RepresentativeStockBalance,
    StockDocument,
    Warehouse,
    WarehouseStockBalance,
)
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
    representative_balances,
    representative_debt,
)


pytestmark = pytest.mark.skipif(
    not settings.database_url.startswith(("postgresql://", "postgresql+psycopg://")),
    reason="Конкурентная проверка требует PostgreSQL и блокировок SELECT FOR UPDATE",
)

WORKERS = 8
QUANTITY_PER_OPERATION = Decimal("2.000")
INITIAL_QUANTITY = Decimal("10.000")


def test_concurrent_issue_cannot_overdraw_warehouse_balance():
    with SessionLocal() as session:
        warehouse = Warehouse(code="LOAD-WH", name="Склад конкурентной проверки")
        product = Product(
            sku="LOAD-ISSUE",
            name="Товар конкурентной выдачи",
            unit="шт",
            retail_price=Decimal("100.00"),
            wholesale_price=Decimal("80.00"),
        )
        representatives = [
            Representative(code=f"LOAD-REP-{index}", name=f"Представитель {index}")
            for index in range(WORKERS)
        ]
        session.add_all([warehouse, product, *representatives])
        session.commit()

        receive_goods(
            session,
            ReceiptRequest(
                warehouse_id=warehouse.id,
                external_id="load-receipt-issue",
                lines=[QuantityLine(product_id=product.id, quantity=INITIAL_QUANTITY)],
            ),
        )
        warehouse_id = warehouse.id
        product_id = product.id
        representative_ids = [row.id for row in representatives]

    barrier = Barrier(WORKERS)

    def issue(index: int) -> str:
        with SessionLocal() as session:
            barrier.wait()
            try:
                issue_to_representative(
                    session,
                    IssueRequest(
                        warehouse_id=warehouse_id,
                        representative_id=representative_ids[index],
                        external_id=f"load-issue-{index}",
                        lines=[
                            QuantityLine(
                                product_id=product_id,
                                quantity=QUANTITY_PER_OPERATION,
                            )
                        ],
                    ),
                )
            except ConflictError:
                session.rollback()
                return "conflict"
            return "success"

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(issue, range(WORKERS)))

    assert results.count("success") == 5
    assert results.count("conflict") == 3

    with SessionLocal() as session:
        warehouse_balance = session.scalar(
            select(WarehouseStockBalance).where(
                WarehouseStockBalance.warehouse_id == warehouse_id,
                WarehouseStockBalance.product_id == product_id,
            )
        )
        assert warehouse_balance is not None
        assert Decimal(warehouse_balance.quantity) == Decimal("0.000")

        representative_total = sum(
            (
                sum(
                    (line.quantity for line in representative_balances(session, representative_id)),
                    Decimal("0"),
                )
                for representative_id in representative_ids
            ),
            Decimal("0"),
        )
        assert representative_total == INITIAL_QUANTITY

        posted_issues = session.scalar(
            select(func.count(StockDocument.id)).where(
                StockDocument.document_type == DocumentType.ISSUE_TO_REPRESENTATIVE,
                StockDocument.status == DocumentStatus.POSTED,
                StockDocument.external_id.like("load-issue-%"),
            )
        )
        assert posted_issues == 5


def test_concurrent_sales_cannot_overdraw_representative_balance_or_debt():
    with SessionLocal() as session:
        warehouse = Warehouse(code="LOAD-SALE-WH", name="Склад конкурентных продаж")
        representative = Representative(code="LOAD-SALE-REP", name="Представитель продаж")
        product = Product(
            sku="LOAD-SALE",
            name="Товар конкурентной продажи",
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
                external_id="load-receipt-sale",
                lines=[QuantityLine(product_id=product.id, quantity=INITIAL_QUANTITY)],
            ),
        )
        issue_to_representative(
            session,
            IssueRequest(
                warehouse_id=warehouse.id,
                representative_id=representative.id,
                external_id="load-prepare-sale",
                lines=[QuantityLine(product_id=product.id, quantity=INITIAL_QUANTITY)],
            ),
        )
        representative_id = representative.id
        product_id = product.id

    barrier = Barrier(WORKERS)

    def sell(index: int) -> str:
        with SessionLocal() as session:
            barrier.wait()
            try:
                register_sale(
                    session,
                    SaleRequest(
                        representative_id=representative_id,
                        external_id=f"load-sale-{index}",
                        lines=[
                            SaleLine(
                                product_id=product_id,
                                quantity=QUANTITY_PER_OPERATION,
                            )
                        ],
                    ),
                )
            except ConflictError:
                session.rollback()
                return "conflict"
            return "success"

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(sell, range(WORKERS)))

    assert results.count("success") == 5
    assert results.count("conflict") == 3

    with SessionLocal() as session:
        representative_balance = session.scalar(
            select(RepresentativeStockBalance).where(
                RepresentativeStockBalance.representative_id == representative_id,
                RepresentativeStockBalance.product_id == product_id,
            )
        )
        assert representative_balance is not None
        assert Decimal(representative_balance.quantity) == Decimal("0.000")
        assert representative_balances(session, representative_id) == []
        assert representative_debt(session, representative_id).debt == Decimal("1000.00")

        posted_sales = session.scalar(
            select(func.count(StockDocument.id)).where(
                StockDocument.document_type == DocumentType.SALE,
                StockDocument.status == DocumentStatus.POSTED,
                StockDocument.external_id.like("load-sale-%"),
            )
        )
        assert posted_sales == 5


def test_same_external_id_is_idempotent_under_concurrent_stock_requests():
    with SessionLocal() as session:
        warehouse = Warehouse(code="IDEM-WH", name="Склад идемпотентности")
        representative = Representative(code="IDEM-REP", name="Представитель идемпотентности")
        product = Product(
            sku="IDEM-SKU",
            name="Товар идемпотентности",
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
                external_id="idem-prepare-stock",
                lines=[QuantityLine(product_id=product.id, quantity=Decimal("10.000"))],
            ),
        )
        warehouse_id = warehouse.id
        representative_id = representative.id
        product_id = product.id

    barrier = Barrier(2)

    def issue_same_request(_: int):
        with SessionLocal() as session:
            barrier.wait()
            return issue_to_representative(
                session,
                IssueRequest(
                    warehouse_id=warehouse_id,
                    representative_id=representative_id,
                    external_id="idem-concurrent-issue",
                    lines=[QuantityLine(product_id=product_id, quantity=Decimal("2.000"))],
                ),
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(issue_same_request, range(2)))

    assert results[0].document_id is not None
    assert results[0].document_id == results[1].document_id

    with SessionLocal() as session:
        warehouse_balance = session.scalar(
            select(WarehouseStockBalance).where(
                WarehouseStockBalance.warehouse_id == warehouse_id,
                WarehouseStockBalance.product_id == product_id,
            )
        )
        representative_balance = session.scalar(
            select(RepresentativeStockBalance).where(
                RepresentativeStockBalance.representative_id == representative_id,
                RepresentativeStockBalance.product_id == product_id,
            )
        )
        assert warehouse_balance is not None
        assert representative_balance is not None
        assert Decimal(warehouse_balance.quantity) == Decimal("8.000")
        assert Decimal(representative_balance.quantity) == Decimal("2.000")
        assert session.scalar(
            select(func.count(StockDocument.id)).where(
                StockDocument.external_id == "idem-concurrent-issue"
            )
        ) == 1


def test_same_external_id_is_idempotent_under_concurrent_payments():
    with SessionLocal() as session:
        representative = Representative(code="IDEM-PAY-REP", name="Представитель платежа")
        session.add(representative)
        session.commit()
        representative_id = representative.id

    barrier = Barrier(2)

    def pay_same_request(_: int):
        with SessionLocal() as session:
            barrier.wait()
            return register_payment(
                session,
                PaymentRequest(
                    representative_id=representative_id,
                    amount=Decimal("100.00"),
                    external_id="idem-concurrent-payment",
                ),
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pay_same_request, range(2)))

    assert results[0].money_posting_id is not None
    assert results[0].money_posting_id == results[1].money_posting_id
    assert results[0].debt_delta == Decimal("-100.00")
    assert results[1].debt_delta == Decimal("-100.00")

    with SessionLocal() as session:
        assert session.scalar(
            select(func.count(MoneyPosting.id)).where(
                MoneyPosting.external_id == "idem-concurrent-payment"
            )
        ) == 1
        assert representative_debt(session, representative_id).debt == Decimal("-100.00")
