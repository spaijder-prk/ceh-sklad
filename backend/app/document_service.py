from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .document_schemas import DocumentCancelResult, DocumentLineRead, DocumentRead
from .models import (
    DocumentStatus,
    MoneyOperation,
    MoneyPosting,
    Product,
    Representative,
    StockDocument,
    StockPosting,
    Warehouse,
)
from .services import (
    NotFoundError,
    _change_representative_stock,
    _change_warehouse_stock,
    _ensure_representative_stock,
    _ensure_warehouse_stock,
)


def document_journal(
    session: Session,
    limit: int = 100,
    representative_id: UUID | None = None,
) -> list[DocumentRead]:
    statement = select(StockDocument)
    if representative_id is not None:
        representative_documents = select(StockPosting.document_id).where(
            StockPosting.representative_id == representative_id
        )
        statement = statement.where(StockDocument.id.in_(representative_documents))

    documents = session.scalars(
        statement
        .order_by(StockDocument.posted_at.desc(), StockDocument.id.desc())
        .limit(limit)
    ).all()

    result: list[DocumentRead] = []
    for document in documents:
        line_rows = session.execute(
            select(
                StockPosting.product_id,
                Product.sku,
                Product.name,
                StockPosting.warehouse_id,
                Warehouse.name,
                StockPosting.representative_id,
                Representative.name,
                StockPosting.quantity,
                StockPosting.unit_price,
            )
            .join(Product, Product.id == StockPosting.product_id)
            .outerjoin(Warehouse, Warehouse.id == StockPosting.warehouse_id)
            .outerjoin(Representative, Representative.id == StockPosting.representative_id)
            .where(StockPosting.document_id == document.id)
            .order_by(Product.name, StockPosting.id)
        ).all()
        sale_amount = Decimal(
            session.scalar(
                select(func.coalesce(func.sum(MoneyPosting.amount), 0)).where(
                    MoneyPosting.document_id == document.id,
                    MoneyPosting.operation == MoneyOperation.SALE,
                )
            )
            or 0
        )
        result.append(
            DocumentRead(
                id=document.id,
                document_type=document.document_type,
                status=document.status,
                external_id=document.external_id,
                comment=document.comment,
                created_at=document.created_at,
                posted_at=document.posted_at,
                sale_amount=sale_amount,
                lines=[
                    DocumentLineRead(
                        product_id=row[0],
                        sku=row[1],
                        product_name=row[2],
                        warehouse_id=row[3],
                        warehouse_name=row[4],
                        representative_id=row[5],
                        representative_name=row[6],
                        quantity=row[7],
                        unit_price=row[8],
                    )
                    for row in line_rows
                ],
            )
        )
    return result


def cancel_document(session: Session, document_id: UUID) -> DocumentCancelResult:
    document = session.scalar(
        select(StockDocument).where(StockDocument.id == document_id).with_for_update()
    )
    if document is None:
        raise NotFoundError("Документ не найден")
    if document.status == DocumentStatus.CANCELLED:
        return DocumentCancelResult(
            document_id=document.id,
            status=document.status,
            stock_changed=False,
            debt_changed=False,
        )

    postings = session.scalars(
        select(StockPosting)
        .where(StockPosting.document_id == document.id)
        .order_by(StockPosting.id)
    ).all()

    # До изменения регистра проверяем все будущие списания, чтобы сторно было атомарным.
    warehouse_required: dict[UUID, dict[UUID, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0"))
    )
    representative_required: dict[UUID, dict[UUID, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0"))
    )
    for posting in postings:
        quantity = Decimal(posting.quantity)
        if quantity <= 0:
            continue
        if posting.warehouse_id is not None:
            warehouse_required[posting.warehouse_id][posting.product_id] += quantity
        elif posting.representative_id is not None:
            representative_required[posting.representative_id][posting.product_id] += quantity

    for warehouse_id in sorted(warehouse_required, key=str):
        _ensure_warehouse_stock(session, warehouse_id, dict(warehouse_required[warehouse_id]))
    for representative_id in sorted(representative_required, key=str):
        _ensure_representative_stock(
            session,
            representative_id,
            dict(representative_required[representative_id]),
        )

    for posting in postings:
        reverse_quantity = -Decimal(posting.quantity)
        if posting.warehouse_id is not None:
            _change_warehouse_stock(
                session,
                posting.warehouse_id,
                posting.product_id,
                reverse_quantity,
            )
        elif posting.representative_id is not None:
            _change_representative_stock(
                session,
                posting.representative_id,
                posting.product_id,
                reverse_quantity,
            )

    money_rows = session.scalars(
        select(MoneyPosting).where(MoneyPosting.document_id == document.id)
    ).all()
    amounts_by_representative: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    for posting in money_rows:
        amounts_by_representative[posting.representative_id] += Decimal(posting.amount)

    debt_changed = False
    for representative_id, amount in amounts_by_representative.items():
        if amount == 0:
            continue
        session.add(
            MoneyPosting(
                representative_id=representative_id,
                document_id=document.id,
                operation=MoneyOperation.ADJUSTMENT,
                amount=-amount,
                comment=f"Сторно документа {document.id}",
                external_id=f"cancel-{document.id}-{representative_id}",
            )
        )
        debt_changed = True

    document.status = DocumentStatus.CANCELLED
    session.commit()
    return DocumentCancelResult(
        document_id=document.id,
        status=document.status,
        stock_changed=bool(postings),
        debt_changed=debt_changed,
    )
