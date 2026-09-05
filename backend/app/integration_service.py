from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as BinasciiError
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .document_service import document_journal
from .integration_schemas import OneCDocumentPage, OneCMoneyPostingPage, OneCSnapshot
from .models import Product, Representative, Warehouse
from .money_service import money_journal
from .services import representative_balances, representative_debt, warehouse_balances


def build_1c_snapshot(session: Session) -> OneCSnapshot:
    representatives = session.scalars(select(Representative).order_by(Representative.name)).all()
    return OneCSnapshot(
        generated_at=datetime.now(UTC),
        warehouses=session.scalars(select(Warehouse).order_by(Warehouse.name)).all(),
        products=session.scalars(select(Product).order_by(Product.name)).all(),
        representatives=representatives,
        warehouse_balances=warehouse_balances(session),
        representative_balances=representative_balances(session),
        debts=[representative_debt(session, representative.id) for representative in representatives],
    )


def encode_1c_cursor(moment: datetime, entity_id: UUID) -> str:
    normalized = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)
    raw = f"{normalized.isoformat()}|{entity_id}".encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_1c_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = urlsafe_b64decode((cursor + padding).encode("ascii")).decode("utf-8")
        moment_raw, entity_raw = raw.rsplit("|", 1)
        moment = datetime.fromisoformat(moment_raw)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment.astimezone(UTC), UUID(entity_raw)
    except (BinasciiError, ValueError, UnicodeDecodeError) as error:
        raise ValueError("Некорректный курсор обмена с 1С") from error


def build_1c_document_page(
    session: Session,
    *,
    cursor: str | None,
    limit: int,
) -> OneCDocumentPage:
    after_at = None
    after_id = None
    if cursor:
        after_at, after_id = decode_1c_cursor(cursor)

    rows = document_journal(
        session,
        limit=limit + 1,
        after_updated_at=after_at,
        after_id=after_id,
        ascending=True,
    )
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = cursor
    if items:
        last = items[-1]
        next_cursor = encode_1c_cursor(last.updated_at, last.id)
    return OneCDocumentPage(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


def build_1c_money_posting_page(
    session: Session,
    *,
    cursor: str | None,
    limit: int,
) -> OneCMoneyPostingPage:
    after_at = None
    after_id = None
    if cursor:
        after_at, after_id = decode_1c_cursor(cursor)

    rows = money_journal(
        session,
        limit=limit + 1,
        after_created_at=after_at,
        after_id=after_id,
        ascending=True,
    )
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = cursor
    if items:
        last = items[-1]
        next_cursor = encode_1c_cursor(last.created_at, last.id)
    return OneCMoneyPostingPage(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )
