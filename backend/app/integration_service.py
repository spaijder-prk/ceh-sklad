from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as BinasciiError
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .document_service import document_journal
from .integration_models import OneCEntityLink, OneCEntityType
from .integration_schemas import (
    OneCDocumentPage,
    OneCEntityLinkRead,
    OneCEntityLinkWrite,
    OneCMoneyPostingPage,
    OneCSnapshot,
)
from .models import Product, Representative, Warehouse
from .money_service import money_journal
from .services import (
    ConflictError,
    NotFoundError,
    representative_balances,
    representative_debt,
    warehouse_balances,
)


_ENTITY_META = {
    OneCEntityType.WAREHOUSE: (Warehouse, "Склад", "code", "name"),
    OneCEntityType.PRODUCT: (Product, "Товар", "sku", "name"),
    OneCEntityType.REPRESENTATIVE: (
        Representative,
        "Торговый представитель",
        "code",
        "name",
    ),
}


def _entity_info(
    session: Session,
    entity_type: OneCEntityType,
    backend_id: UUID,
):
    model, label, code_field, name_field = _ENTITY_META[entity_type]
    entity = session.get(model, backend_id)
    if entity is None:
        raise NotFoundError(f"{label} не найден")
    return entity, getattr(entity, code_field), getattr(entity, name_field)


def _link_to_read(session: Session, link: OneCEntityLink) -> OneCEntityLinkRead:
    entity_type = OneCEntityType(link.entity_type)
    _, code, name = _entity_info(session, entity_type, link.backend_id)
    return OneCEntityLinkRead(
        entity_type=entity_type,
        backend_id=link.backend_id,
        external_ref=link.external_ref,
        backend_code=code,
        backend_name=name,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def list_1c_entity_links(session: Session) -> list[OneCEntityLinkRead]:
    links = session.scalars(
        select(OneCEntityLink).order_by(
            OneCEntityLink.entity_type,
            OneCEntityLink.external_ref,
        )
    ).all()
    return [_link_to_read(session, link) for link in links]


def upsert_1c_entity_link(
    session: Session,
    payload: OneCEntityLinkWrite,
) -> OneCEntityLinkRead:
    external_ref = payload.external_ref.strip()
    if not external_ref:
        raise ValueError("Ссылка 1С не может быть пустой")

    _entity_info(session, payload.entity_type, payload.backend_id)

    conflicting = session.scalar(
        select(OneCEntityLink).where(
            OneCEntityLink.entity_type == payload.entity_type,
            OneCEntityLink.external_ref == external_ref,
            OneCEntityLink.backend_id != payload.backend_id,
        )
    )
    if conflicting is not None:
        raise ConflictError(
            "Ссылка 1С уже привязана к другой сущности этого типа"
        )

    link = session.scalar(
        select(OneCEntityLink).where(
            OneCEntityLink.entity_type == payload.entity_type,
            OneCEntityLink.backend_id == payload.backend_id,
        )
    )
    if link is None:
        link = OneCEntityLink(
            entity_type=payload.entity_type,
            backend_id=payload.backend_id,
            external_ref=external_ref,
        )
        session.add(link)
    else:
        link.external_ref = external_ref

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ConflictError(
            "Не удалось сохранить соответствие: ссылка 1С уже используется"
        ) from error
    session.refresh(link)
    return _link_to_read(session, link)


def resolve_1c_entity_link(
    session: Session,
    entity_type: OneCEntityType,
    external_ref: str,
) -> OneCEntityLinkRead:
    normalized_ref = external_ref.strip()
    link = session.scalar(
        select(OneCEntityLink).where(
            OneCEntityLink.entity_type == entity_type,
            OneCEntityLink.external_ref == normalized_ref,
        )
    )
    if link is None:
        raise NotFoundError("Соответствие для ссылки 1С не найдено")
    return _link_to_read(session, link)


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
        entity_links=list_1c_entity_links(session),
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
