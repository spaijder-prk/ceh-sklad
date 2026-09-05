from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from .models import (
    DocumentStatus,
    MoneyOperation,
    MoneyPosting,
    Product,
    Representative,
    RepresentativeStockBalance,
    StockDocument,
    WarehouseStockBalance,
)
from .report_schemas import ReportSummary, RepresentativeReportLine


def _period_bounds(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValueError("Дата начала периода не может быть позже даты окончания")
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    end = (
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        if date_to
        else None
    )
    return start, end


def _apply_datetime_period(statement, column, start: datetime | None, end: datetime | None):
    if start is not None:
        statement = statement.where(column >= start)
    if end is not None:
        statement = statement.where(column < end)
    return statement


def _sales_statement(start: datetime | None, end: datetime | None, representative_id=None):
    statement = (
        select(
            func.coalesce(func.sum(MoneyPosting.amount), 0),
            func.count(distinct(MoneyPosting.document_id)),
        )
        .join(StockDocument, StockDocument.id == MoneyPosting.document_id)
        .where(
            MoneyPosting.operation == MoneyOperation.SALE,
            StockDocument.status == DocumentStatus.POSTED,
        )
    )
    if representative_id is not None:
        statement = statement.where(MoneyPosting.representative_id == representative_id)
    return _apply_datetime_period(statement, StockDocument.posted_at, start, end)


def _payments_statement(start: datetime | None, end: datetime | None, representative_id=None):
    statement = select(func.coalesce(func.sum(-MoneyPosting.amount), 0)).where(
        MoneyPosting.operation == MoneyOperation.PAYMENT
    )
    if representative_id is not None:
        statement = statement.where(MoneyPosting.representative_id == representative_id)
    return _apply_datetime_period(statement, MoneyPosting.created_at, start, end)


def _debt_statement(representative_id=None):
    statement = select(func.coalesce(func.sum(MoneyPosting.amount), 0))
    if representative_id is not None:
        statement = statement.where(MoneyPosting.representative_id == representative_id)
    return statement


def _warehouse_retail_value(session: Session) -> Decimal:
    value = session.scalar(
        select(
            func.coalesce(func.sum(WarehouseStockBalance.quantity * Product.retail_price), 0)
        ).join(Product, Product.id == WarehouseStockBalance.product_id)
    )
    return Decimal(value or 0)


def _representative_stock_retail_value(session: Session, representative_id=None) -> Decimal:
    statement = select(
        func.coalesce(func.sum(RepresentativeStockBalance.quantity * Product.retail_price), 0)
    ).join(Product, Product.id == RepresentativeStockBalance.product_id)
    if representative_id is not None:
        statement = statement.where(
            RepresentativeStockBalance.representative_id == representative_id
        )
    return Decimal(session.scalar(statement) or 0)


def report_summary(
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ReportSummary:
    start, end = _period_bounds(date_from, date_to)
    sales_amount, sales_documents = session.execute(_sales_statement(start, end)).one()
    payments_amount = session.scalar(_payments_statement(start, end))
    current_debt = session.scalar(_debt_statement())
    return ReportSummary(
        date_from=date_from,
        date_to=date_to,
        sales_amount=Decimal(sales_amount or 0),
        sales_documents=int(sales_documents or 0),
        payments_amount=Decimal(payments_amount or 0),
        current_debt=Decimal(current_debt or 0),
        warehouse_retail_value=_warehouse_retail_value(session),
        representative_stock_retail_value=_representative_stock_retail_value(session),
    )


def representative_report(
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[RepresentativeReportLine]:
    start, end = _period_bounds(date_from, date_to)
    representatives = session.scalars(select(Representative).order_by(Representative.name)).all()
    result: list[RepresentativeReportLine] = []
    for representative in representatives:
        sales_amount, sales_documents = session.execute(
            _sales_statement(start, end, representative.id)
        ).one()
        payments_amount = session.scalar(_payments_statement(start, end, representative.id))
        current_debt = session.scalar(_debt_statement(representative.id))
        stock_positions = session.scalar(
            select(func.count())
            .select_from(RepresentativeStockBalance)
            .where(
                RepresentativeStockBalance.representative_id == representative.id,
                RepresentativeStockBalance.quantity != 0,
            )
        )
        result.append(
            RepresentativeReportLine(
                representative_id=representative.id,
                representative_code=representative.code,
                representative_name=representative.name,
                sales_amount=Decimal(sales_amount or 0),
                sales_documents=int(sales_documents or 0),
                payments_amount=Decimal(payments_amount or 0),
                current_debt=Decimal(current_debt or 0),
                stock_positions=int(stock_positions or 0),
                stock_retail_value=_representative_stock_retail_value(session, representative.id),
            )
        )
    return result
