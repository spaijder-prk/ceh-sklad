from collections import defaultdict
from decimal import Decimal
from hashlib import blake2b
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import (
    DocumentStatus,
    DocumentType,
    MoneyOperation,
    MoneyPosting,
    PriceType,
    Product,
    Representative,
    RepresentativeStockBalance,
    StockDocument,
    StockPosting,
    Warehouse,
    WarehouseStockBalance,
)
from .schemas import (
    IssueRequest,
    OperationResult,
    PaymentRequest,
    ReceiptRequest,
    RepresentativeBalanceLine,
    RepresentativeDebt,
    ReturnRequest,
    SaleRequest,
    TransferRequest,
    WarehouseBalanceLine,
)


class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


def _must_exist(session: Session, model, object_id: UUID, label: str):
    obj = session.get(model, object_id)
    if obj is None:
        raise NotFoundError(f"{label} не найден")
    return obj


def _group_quantities(lines) -> dict[UUID, Decimal]:
    grouped: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    for line in lines:
        grouped[line.product_id] += line.quantity
    return dict(grouped)


def _check_products(session: Session, product_ids: set[UUID]) -> dict[UUID, Product]:
    products = session.scalars(select(Product).where(Product.id.in_(product_ids))).all()
    result = {product.id: product for product in products}
    missing = product_ids - set(result)
    if missing:
        raise NotFoundError(f"Не найдены товары: {', '.join(map(str, missing))}")
    return result


def _warehouse_balance_row(
    session: Session,
    warehouse_id: UUID,
    product_id: UUID,
    *,
    lock: bool = False,
) -> WarehouseStockBalance | None:
    statement = select(WarehouseStockBalance).where(
        WarehouseStockBalance.warehouse_id == warehouse_id,
        WarehouseStockBalance.product_id == product_id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _representative_balance_row(
    session: Session,
    representative_id: UUID,
    product_id: UUID,
    *,
    lock: bool = False,
) -> RepresentativeStockBalance | None:
    statement = select(RepresentativeStockBalance).where(
        RepresentativeStockBalance.representative_id == representative_id,
        RepresentativeStockBalance.product_id == product_id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _ensure_warehouse_stock(
    session: Session, warehouse_id: UUID, required: dict[UUID, Decimal]
) -> None:
    for product_id in sorted(required, key=str):
        quantity = required[product_id]
        row = _warehouse_balance_row(session, warehouse_id, product_id, lock=True)
        available = Decimal(row.quantity) if row is not None else Decimal("0")
        if available < quantity:
            raise ConflictError(
                f"Недостаточно товара {product_id} на складе: доступно {available}, требуется {quantity}"
            )


def _ensure_representative_stock(
    session: Session, representative_id: UUID, required: dict[UUID, Decimal]
) -> None:
    for product_id in sorted(required, key=str):
        quantity = required[product_id]
        row = _representative_balance_row(session, representative_id, product_id, lock=True)
        available = Decimal(row.quantity) if row is not None else Decimal("0")
        if available < quantity:
            raise ConflictError(
                f"Недостаточно товара {product_id} у представителя: доступно {available}, требуется {quantity}"
            )


def _change_warehouse_stock(
    session: Session,
    warehouse_id: UUID,
    product_id: UUID,
    delta: Decimal,
) -> None:
    row = _warehouse_balance_row(session, warehouse_id, product_id, lock=True)
    if row is None:
        if delta < 0:
            raise ConflictError(f"Недостаточно товара {product_id} на складе")
        session.add(
            WarehouseStockBalance(
                warehouse_id=warehouse_id,
                product_id=product_id,
                quantity=delta,
            )
        )
        return

    new_quantity = Decimal(row.quantity) + delta
    if new_quantity < 0:
        raise ConflictError(f"Операция приведет к отрицательному остатку товара {product_id} на складе")
    row.quantity = new_quantity


def _change_representative_stock(
    session: Session,
    representative_id: UUID,
    product_id: UUID,
    delta: Decimal,
) -> None:
    row = _representative_balance_row(session, representative_id, product_id, lock=True)
    if row is None:
        if delta < 0:
            raise ConflictError(f"Недостаточно товара {product_id} у представителя")
        session.add(
            RepresentativeStockBalance(
                representative_id=representative_id,
                product_id=product_id,
                quantity=delta,
            )
        )
        return

    new_quantity = Decimal(row.quantity) + delta
    if new_quantity < 0:
        raise ConflictError(
            f"Операция приведет к отрицательному остатку товара {product_id} у представителя"
        )
    row.quantity = new_quantity


def _lock_external_id(session: Session, external_id: str | None) -> None:
    if not external_id or session.get_bind().dialect.name != "postgresql":
        return

    # Транзакционная advisory-блокировка сериализует только одинаковые external_id.
    # Она снимается автоматически при commit/rollback и не требует отдельной таблицы блокировок.
    digest = blake2b(
        external_id.encode("utf-8"),
        digest_size=8,
        person=b"ceh-idem",
    ).digest()
    lock_key = int.from_bytes(digest, byteorder="big", signed=True)
    session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )


def _find_existing_document(session: Session, external_id: str | None) -> StockDocument | None:
    if not external_id:
        return None
    return session.scalar(select(StockDocument).where(StockDocument.external_id == external_id))


def _new_document(
    *, document_type: DocumentType, comment: str | None, external_id: str | None
) -> StockDocument:
    return StockDocument(
        document_type=document_type,
        status=DocumentStatus.POSTED,
        comment=comment,
        external_id=external_id,
    )


def receive_goods(session: Session, payload: ReceiptRequest) -> OperationResult:
    _lock_external_id(session, payload.external_id)
    existing = _find_existing_document(session, payload.external_id)
    if existing:
        return OperationResult(document_id=existing.id)

    _must_exist(session, Warehouse, payload.warehouse_id, "Склад")
    grouped = _group_quantities(payload.lines)
    _check_products(session, set(grouped))

    for product_id, quantity in grouped.items():
        _change_warehouse_stock(session, payload.warehouse_id, product_id, quantity)

    document = _new_document(
        document_type=DocumentType.RECEIPT,
        comment=payload.comment,
        external_id=payload.external_id,
    )
    session.add(document)
    session.flush()
    for product_id, quantity in grouped.items():
        session.add(
            StockPosting(
                document_id=document.id,
                product_id=product_id,
                warehouse_id=payload.warehouse_id,
                quantity=quantity,
            )
        )
    session.commit()
    return OperationResult(document_id=document.id)


def issue_to_representative(session: Session, payload: IssueRequest) -> OperationResult:
    _lock_external_id(session, payload.external_id)
    existing = _find_existing_document(session, payload.external_id)
    if existing:
        return OperationResult(document_id=existing.id)

    _must_exist(session, Warehouse, payload.warehouse_id, "Склад")
    _must_exist(session, Representative, payload.representative_id, "Торговый представитель")
    grouped = _group_quantities(payload.lines)
    _check_products(session, set(grouped))
    _ensure_warehouse_stock(session, payload.warehouse_id, grouped)

    for product_id, quantity in grouped.items():
        _change_warehouse_stock(session, payload.warehouse_id, product_id, -quantity)
        _change_representative_stock(session, payload.representative_id, product_id, quantity)

    document = _new_document(
        document_type=DocumentType.ISSUE_TO_REPRESENTATIVE,
        comment=payload.comment,
        external_id=payload.external_id,
    )
    session.add(document)
    session.flush()
    for product_id, quantity in grouped.items():
        session.add_all(
            [
                StockPosting(
                    document_id=document.id,
                    product_id=product_id,
                    warehouse_id=payload.warehouse_id,
                    quantity=-quantity,
                ),
                StockPosting(
                    document_id=document.id,
                    product_id=product_id,
                    representative_id=payload.representative_id,
                    quantity=quantity,
                ),
            ]
        )
    session.commit()
    return OperationResult(document_id=document.id)


def transfer_between_warehouses(session: Session, payload: TransferRequest) -> OperationResult:
    _lock_external_id(session, payload.external_id)
    existing = _find_existing_document(session, payload.external_id)
    if existing:
        return OperationResult(document_id=existing.id)

    _must_exist(session, Warehouse, payload.source_warehouse_id, "Склад-источник")
    _must_exist(session, Warehouse, payload.target_warehouse_id, "Склад-получатель")
    grouped = _group_quantities(payload.lines)
    _check_products(session, set(grouped))
    _ensure_warehouse_stock(session, payload.source_warehouse_id, grouped)

    for product_id, quantity in grouped.items():
        _change_warehouse_stock(session, payload.source_warehouse_id, product_id, -quantity)
        _change_warehouse_stock(session, payload.target_warehouse_id, product_id, quantity)

    document = _new_document(
        document_type=DocumentType.WAREHOUSE_TRANSFER,
        comment=payload.comment,
        external_id=payload.external_id,
    )
    session.add(document)
    session.flush()
    for product_id, quantity in grouped.items():
        session.add_all(
            [
                StockPosting(
                    document_id=document.id,
                    product_id=product_id,
                    warehouse_id=payload.source_warehouse_id,
                    quantity=-quantity,
                ),
                StockPosting(
                    document_id=document.id,
                    product_id=product_id,
                    warehouse_id=payload.target_warehouse_id,
                    quantity=quantity,
                ),
            ]
        )
    session.commit()
    return OperationResult(document_id=document.id)


def return_from_representative(session: Session, payload: ReturnRequest) -> OperationResult:
    _lock_external_id(session, payload.external_id)
    existing = _find_existing_document(session, payload.external_id)
    if existing:
        return OperationResult(document_id=existing.id)

    _must_exist(session, Representative, payload.representative_id, "Торговый представитель")
    _must_exist(session, Warehouse, payload.warehouse_id, "Склад")
    grouped = _group_quantities(payload.lines)
    _check_products(session, set(grouped))
    _ensure_representative_stock(session, payload.representative_id, grouped)

    for product_id, quantity in grouped.items():
        _change_representative_stock(session, payload.representative_id, product_id, -quantity)
        _change_warehouse_stock(session, payload.warehouse_id, product_id, quantity)

    document = _new_document(
        document_type=DocumentType.REPRESENTATIVE_RETURN,
        comment=payload.comment,
        external_id=payload.external_id,
    )
    session.add(document)
    session.flush()
    for product_id, quantity in grouped.items():
        session.add_all(
            [
                StockPosting(
                    document_id=document.id,
                    product_id=product_id,
                    representative_id=payload.representative_id,
                    quantity=-quantity,
                ),
                StockPosting(
                    document_id=document.id,
                    product_id=product_id,
                    warehouse_id=payload.warehouse_id,
                    quantity=quantity,
                ),
            ]
        )
    session.commit()
    return OperationResult(document_id=document.id)


def register_sale(session: Session, payload: SaleRequest) -> OperationResult:
    _lock_external_id(session, payload.external_id)
    existing = _find_existing_document(session, payload.external_id)
    if existing:
        debt_delta = Decimal(
            session.scalar(
                select(func.coalesce(func.sum(MoneyPosting.amount), 0)).where(
                    MoneyPosting.document_id == existing.id,
                    MoneyPosting.operation == MoneyOperation.SALE,
                )
            )
            or 0
        )
        return OperationResult(document_id=existing.id, debt_delta=debt_delta)

    _must_exist(session, Representative, payload.representative_id, "Торговый представитель")
    required = _group_quantities(payload.lines)
    products = _check_products(session, set(required))
    _ensure_representative_stock(session, payload.representative_id, required)

    for product_id, quantity in required.items():
        _change_representative_stock(session, payload.representative_id, product_id, -quantity)

    document = _new_document(
        document_type=DocumentType.SALE,
        comment=payload.comment,
        external_id=payload.external_id,
    )
    session.add(document)
    session.flush()

    debt_delta = Decimal("0")
    for line in payload.lines:
        product = products[line.product_id]
        unit_price = (
            product.retail_price if line.price_type == PriceType.RETAIL else product.wholesale_price
        )
        debt_delta += line.quantity * unit_price
        session.add(
            StockPosting(
                document_id=document.id,
                product_id=line.product_id,
                representative_id=payload.representative_id,
                quantity=-line.quantity,
                unit_price=unit_price,
            )
        )

    session.add(
        MoneyPosting(
            representative_id=payload.representative_id,
            document_id=document.id,
            operation=MoneyOperation.SALE,
            amount=debt_delta,
            comment=payload.comment,
        )
    )
    session.commit()
    return OperationResult(document_id=document.id, debt_delta=debt_delta)


def register_payment(session: Session, payload: PaymentRequest) -> OperationResult:
    _lock_external_id(session, payload.external_id)
    if payload.external_id:
        existing = session.scalar(
            select(MoneyPosting).where(MoneyPosting.external_id == payload.external_id)
        )
        if existing:
            return OperationResult(
                money_posting_id=existing.id,
                debt_delta=existing.amount,
            )

    _must_exist(session, Representative, payload.representative_id, "Торговый представитель")
    posting = MoneyPosting(
        representative_id=payload.representative_id,
        operation=MoneyOperation.PAYMENT,
        amount=-payload.amount,
        comment=payload.comment,
        external_id=payload.external_id,
    )
    session.add(posting)
    session.commit()
    return OperationResult(money_posting_id=posting.id, debt_delta=-payload.amount)


def warehouse_balances(session: Session, warehouse_id: UUID | None = None) -> list[WarehouseBalanceLine]:
    statement = (
        select(
            Warehouse.id,
            Warehouse.code,
            Warehouse.name,
            Product.id,
            Product.sku,
            Product.name,
            Product.unit,
            Product.retail_price,
            Product.wholesale_price,
            WarehouseStockBalance.quantity,
        )
        .join(WarehouseStockBalance, WarehouseStockBalance.warehouse_id == Warehouse.id)
        .join(Product, Product.id == WarehouseStockBalance.product_id)
        .where(WarehouseStockBalance.quantity != 0)
        .order_by(Warehouse.name, Product.name)
    )
    if warehouse_id is not None:
        statement = statement.where(Warehouse.id == warehouse_id)

    return [
        WarehouseBalanceLine(
            warehouse_id=row[0],
            warehouse_code=row[1],
            warehouse_name=row[2],
            product_id=row[3],
            sku=row[4],
            product_name=row[5],
            unit=row[6],
            retail_price=row[7],
            wholesale_price=row[8],
            quantity=row[9],
        )
        for row in session.execute(statement)
    ]


def representative_balances(
    session: Session, representative_id: UUID | None = None
) -> list[RepresentativeBalanceLine]:
    statement = (
        select(
            Representative.id,
            Representative.code,
            Representative.name,
            Product.id,
            Product.sku,
            Product.name,
            Product.unit,
            Product.retail_price,
            Product.wholesale_price,
            RepresentativeStockBalance.quantity,
        )
        .join(
            RepresentativeStockBalance,
            RepresentativeStockBalance.representative_id == Representative.id,
        )
        .join(Product, Product.id == RepresentativeStockBalance.product_id)
        .where(RepresentativeStockBalance.quantity != 0)
        .order_by(Representative.name, Product.name)
    )
    if representative_id is not None:
        statement = statement.where(Representative.id == representative_id)

    return [
        RepresentativeBalanceLine(
            representative_id=row[0],
            representative_code=row[1],
            representative_name=row[2],
            product_id=row[3],
            sku=row[4],
            product_name=row[5],
            unit=row[6],
            retail_price=row[7],
            wholesale_price=row[8],
            quantity=row[9],
        )
        for row in session.execute(statement)
    ]


def representative_debt(session: Session, representative_id: UUID) -> RepresentativeDebt:
    _must_exist(session, Representative, representative_id, "Торговый представитель")
    debt = Decimal(
        session.scalar(
            select(func.coalesce(func.sum(MoneyPosting.amount), 0)).where(
                MoneyPosting.representative_id == representative_id
            )
        )
        or 0
    )
    return RepresentativeDebt(representative_id=representative_id, debt=debt)