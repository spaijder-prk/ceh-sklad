from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import get_session
from .models import (
    IntegrationExchangeLog,
    InventoryBalance,
    Location,
    LocationKind,
    MoneyTransaction,
    MoneyTransactionKind,
    Product,
    StockDocument,
    StockDocumentLine,
)
from .schemas import AdjustmentItemIn
from .services import create_adjustment


async def require_1c_key(x_1c_key: str | None = Header(default=None, alias="X-1C-Key")) -> None:
    configured = settings.integration_1c_api_key
    if not configured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Интеграция с 1С не настроена")
    if not x_1c_key or not hmac.compare_digest(x_1c_key, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный ключ интеграции 1С")


router = APIRouter(
    prefix="/api/v1/integration/1c",
    tags=["Интеграция 1С"],
    dependencies=[Depends(require_1c_key)],
)


class ImportProductIn(BaseModel):
    operation_key: str = Field(min_length=8, max_length=120)
    external_1c_id: str = Field(min_length=1, max_length=100)
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=200)
    unit_name: str = Field(default="шт", min_length=1, max_length=30)
    retail_price: Decimal = Field(ge=0)
    wholesale_price: Decimal = Field(ge=0)
    is_active: bool = True


class ImportLocationIn(BaseModel):
    operation_key: str = Field(min_length=8, max_length=120)
    external_1c_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=2, max_length=150)
    kind: LocationKind


class ImportAdjustmentItemIn(BaseModel):
    product_external_1c_id: str = Field(min_length=1, max_length=100)
    quantity_delta: Decimal


class ImportAdjustmentIn(BaseModel):
    operation_key: str = Field(min_length=8, max_length=120)
    external_1c_id: str = Field(min_length=1, max_length=100)
    location_external_1c_id: str = Field(min_length=1, max_length=100)
    items: list[ImportAdjustmentItemIn]
    comment: str = Field(min_length=3, max_length=500)


class ImportResult(BaseModel):
    internal_id: UUID
    repeated: bool = False


class OutboxLine(BaseModel):
    product_id: UUID
    product_external_1c_id: str | None
    sku: str
    quantity: Decimal
    unit_price: Decimal | None = None


class OutboxItem(BaseModel):
    entity_type: Literal["stock_document", "cash_handover"]
    internal_id: UUID
    kind: str
    created_at: datetime
    source_location_external_1c_id: str | None = None
    destination_location_external_1c_id: str | None = None
    representative_external_1c_id: str | None = None
    amount: Decimal | None = None
    comment: str | None = None
    lines: list[OutboxLine] = Field(default_factory=list)


class ConfirmExportIn(BaseModel):
    entity_type: Literal["stock_document", "cash_handover"]
    internal_id: UUID
    external_1c_id: str = Field(min_length=1, max_length=100)


def _payload_data(payload: BaseModel) -> dict:
    return payload.model_dump(mode="json")


def _payload_hash(payload: BaseModel) -> str:
    raw = json.dumps(_payload_data(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _product_total_stock(session: AsyncSession, product_id: UUID) -> Decimal:
    value = await session.scalar(
        select(func.coalesce(func.sum(InventoryBalance.quantity), 0)).where(
            InventoryBalance.product_id == product_id
        )
    )
    return Decimal(value)


async def _begin_import(
    session: AsyncSession,
    *,
    operation_key: str,
    entity_type: str,
    external_1c_id: str,
    payload: BaseModel,
) -> tuple[IntegrationExchangeLog, bool]:
    payload_hash = _payload_hash(payload)
    existing = await session.scalar(select(IntegrationExchangeLog).where(IntegrationExchangeLog.operation_key == operation_key))
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ключ операции уже использован с другим содержимым")
        if existing.status == "completed" and existing.entity_internal_id is not None:
            return existing, True
        if existing.status == "processing":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Операция с таким ключом уже выполняется")
        existing.status = "processing"
        existing.error_message = None
        existing.completed_at = None
        existing.payload = _payload_data(payload)
        await session.flush()
        return existing, False

    log = IntegrationExchangeLog(
        direction="inbound",
        operation_key=operation_key,
        entity_type=entity_type,
        external_1c_id=external_1c_id,
        payload_hash=payload_hash,
        status="processing",
        payload=_payload_data(payload),
    )
    session.add(log)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Операция с таким ключом выполняется параллельно") from exc
    return log, False


async def _mark_failed(session: AsyncSession, payload: BaseModel, entity_type: str, message: str) -> None:
    await session.rollback()
    operation_key = payload.operation_key  # type: ignore[attr-defined]
    existing = await session.scalar(select(IntegrationExchangeLog).where(IntegrationExchangeLog.operation_key == operation_key))
    if existing is None:
        existing = IntegrationExchangeLog(
            direction="inbound",
            operation_key=operation_key,
            entity_type=entity_type,
            external_1c_id=payload.external_1c_id,  # type: ignore[attr-defined]
            payload_hash=_payload_hash(payload),
            status="failed",
            payload=_payload_data(payload),
            error_message=message[:1000],
            completed_at=datetime.now(UTC),
        )
        session.add(existing)
    elif existing.status != "completed":
        existing.status = "failed"
        existing.error_message = message[:1000]
        existing.completed_at = datetime.now(UTC)
    await session.commit()


@router.post("/products", response_model=ImportResult)
async def import_product(payload: ImportProductIn, session: AsyncSession = Depends(get_session)) -> ImportResult:
    log, repeated = await _begin_import(
        session,
        operation_key=payload.operation_key,
        entity_type="product",
        external_1c_id=payload.external_1c_id,
        payload=payload,
    )
    if repeated:
        return ImportResult(internal_id=log.entity_internal_id, repeated=True)  # type: ignore[arg-type]
    try:
        product = await session.scalar(select(Product).where(Product.external_1c_id == payload.external_1c_id))
        sku_owner = await session.scalar(select(Product).where(Product.sku == payload.sku))
        if sku_owner is not None and (product is None or sku_owner.id != product.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Артикул уже принадлежит другому товару")
        if product is None:
            product = Product(external_1c_id=payload.external_1c_id, sku=payload.sku, name=payload.name)
            session.add(product)
        elif not payload.is_active:
            total_stock = await _product_total_stock(session, product.id)
            if total_stock != 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Нельзя архивировать товар с ненулевым остатком {total_stock}. Сначала обнулите остатки",
                )
        product.sku = payload.sku
        product.name = payload.name
        product.unit_name = payload.unit_name
        product.retail_price = payload.retail_price
        product.wholesale_price = payload.wholesale_price
        product.is_active = payload.is_active
        await session.flush()
        log.entity_internal_id = product.id
        log.status = "completed"
        log.completed_at = datetime.now(UTC)
        await session.commit()
        return ImportResult(internal_id=product.id)
    except HTTPException as exc:
        await _mark_failed(session, payload, "product", str(exc.detail))
        raise
    except IntegrityError as exc:
        await _mark_failed(session, payload, "product", "Конфликт уникальности справочника")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Конфликт уникальности справочника") from exc


@router.post("/locations", response_model=ImportResult)
async def import_location(payload: ImportLocationIn, session: AsyncSession = Depends(get_session)) -> ImportResult:
    log, repeated = await _begin_import(
        session,
        operation_key=payload.operation_key,
        entity_type="location",
        external_1c_id=payload.external_1c_id,
        payload=payload,
    )
    if repeated:
        return ImportResult(internal_id=log.entity_internal_id, repeated=True)  # type: ignore[arg-type]
    try:
        location = await session.scalar(select(Location).where(Location.external_1c_id == payload.external_1c_id))
        name_owner = await session.scalar(select(Location).where(Location.name == payload.name))
        if name_owner is not None and (location is None or name_owner.id != location.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Название уже принадлежит другому месту хранения")
        if location is None:
            location = Location(external_1c_id=payload.external_1c_id, name=payload.name, kind=payload.kind)
            session.add(location)
        elif location.kind != payload.kind:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Тип существующего места хранения нельзя изменять через обмен 1С; создайте отдельное место хранения",
            )
        location.name = payload.name
        await session.flush()
        log.entity_internal_id = location.id
        log.status = "completed"
        log.completed_at = datetime.now(UTC)
        await session.commit()
        return ImportResult(internal_id=location.id)
    except HTTPException as exc:
        await _mark_failed(session, payload, "location", str(exc.detail))
        raise
    except IntegrityError as exc:
        await _mark_failed(session, payload, "location", "Конфликт уникальности справочника")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Конфликт уникальности справочника") from exc


@router.post("/stock-adjustments", response_model=ImportResult)
async def import_stock_adjustment(payload: ImportAdjustmentIn, session: AsyncSession = Depends(get_session)) -> ImportResult:
    log, repeated = await _begin_import(
        session,
        operation_key=payload.operation_key,
        entity_type="stock_adjustment",
        external_1c_id=payload.external_1c_id,
        payload=payload,
    )
    if repeated:
        return ImportResult(internal_id=log.entity_internal_id, repeated=True)  # type: ignore[arg-type]
    try:
        existing_document = await session.scalar(
            select(StockDocument).where(StockDocument.external_1c_id == payload.external_1c_id)
        )
        if existing_document is not None:
            log.entity_internal_id = existing_document.id
            log.status = "completed"
            log.completed_at = datetime.now(UTC)
            await session.commit()
            return ImportResult(internal_id=existing_document.id, repeated=True)

        location = await session.scalar(select(Location).where(Location.external_1c_id == payload.location_external_1c_id))
        if location is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Место хранения из 1С не найдено")
        if not location.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя корректировать остатки архивного места хранения",
            )

        items: list[AdjustmentItemIn] = []
        for row in payload.items:
            product = await session.scalar(select(Product).where(Product.external_1c_id == row.product_external_1c_id))
            if product is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Товар 1С {row.product_external_1c_id} не найден",
                )
            if not product.is_active:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Нельзя корректировать остаток архивного товара {product.sku}",
                )
            items.append(AdjustmentItemIn(product_id=product.id, quantity_delta=row.quantity_delta))

        document = await create_adjustment(
            session,
            location_id=location.id,
            items=items,
            comment=payload.comment,
            created_by_id=None,
            external_1c_id=payload.external_1c_id,
            mark_synced_1c=True,
            commit=False,
        )
        log.entity_internal_id = document.id
        log.status = "completed"
        log.completed_at = datetime.now(UTC)
        await session.commit()
        return ImportResult(internal_id=document.id)
    except HTTPException as exc:
        await _mark_failed(session, payload, "stock_adjustment", str(exc.detail))
        raise
    except IntegrityError as exc:
        await _mark_failed(session, payload, "stock_adjustment", "Документ с таким идентификатором уже существует")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Документ с таким идентификатором уже существует") from exc


@router.get("/outbox", response_model=list[OutboxItem])
async def outbox(limit: int = 50, session: AsyncSession = Depends(get_session)) -> list[OutboxItem]:
    limit = max(1, min(limit, 100))
    result: list[OutboxItem] = []
    documents = list(
        await session.scalars(
            select(StockDocument)
            .where(StockDocument.synced_1c_at.is_(None), StockDocument.external_1c_id.is_(None))
            .order_by(StockDocument.created_at, StockDocument.id)
            .limit(limit)
        )
    )
    for document in documents:
        source = await session.get(Location, document.source_location_id) if document.source_location_id else None
        destination = await session.get(Location, document.destination_location_id) if document.destination_location_id else None
        line_rows = (
            await session.execute(
                select(StockDocumentLine, Product)
                .join(Product, Product.id == StockDocumentLine.product_id)
                .where(StockDocumentLine.document_id == document.id)
                .order_by(Product.sku)
            )
        ).all()
        result.append(
            OutboxItem(
                entity_type="stock_document",
                internal_id=document.id,
                kind=document.kind.value,
                created_at=document.created_at,
                source_location_external_1c_id=source.external_1c_id if source else None,
                destination_location_external_1c_id=destination.external_1c_id if destination else None,
                comment=document.comment,
                lines=[
                    OutboxLine(
                        product_id=product.id,
                        product_external_1c_id=product.external_1c_id,
                        sku=product.sku,
                        quantity=line.quantity,
                        unit_price=line.unit_price,
                    )
                    for line, product in line_rows
                ],
            )
        )

    remaining = limit - len(result)
    if remaining > 0:
        handovers = list(
            await session.scalars(
                select(MoneyTransaction)
                .where(
                    MoneyTransaction.kind == MoneyTransactionKind.CASH_HANDOVER,
                    MoneyTransaction.synced_1c_at.is_(None),
                    MoneyTransaction.external_1c_id.is_(None),
                )
                .order_by(MoneyTransaction.created_at, MoneyTransaction.id)
                .limit(remaining)
            )
        )
        for transaction in handovers:
            representative = await session.get(Location, transaction.representative_location_id)
            result.append(
                OutboxItem(
                    entity_type="cash_handover",
                    internal_id=transaction.id,
                    kind=transaction.kind.value,
                    created_at=transaction.created_at,
                    representative_external_1c_id=representative.external_1c_id if representative else None,
                    amount=-transaction.amount,
                    comment=transaction.comment,
                )
            )
    return result


@router.post("/confirm-export", response_model=ImportResult)
async def confirm_export(payload: ConfirmExportIn, session: AsyncSession = Depends(get_session)) -> ImportResult:
    now = datetime.now(UTC)
    operation_key = f"confirm:{payload.entity_type}:{payload.internal_id}"
    if payload.entity_type == "stock_document":
        entity = await session.get(StockDocument, payload.internal_id)
    else:
        entity = await session.get(MoneyTransaction, payload.internal_id)
        if entity is not None and entity.kind != MoneyTransactionKind.CASH_HANDOVER:
            entity = None
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Объект экспорта не найден")
    if entity.external_1c_id is not None:
        if entity.external_1c_id != payload.external_1c_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Объект уже подтвержден другим идентификатором 1С")
        return ImportResult(internal_id=entity.id, repeated=True)

    entity.external_1c_id = payload.external_1c_id
    entity.synced_1c_at = now
    log = await session.scalar(select(IntegrationExchangeLog).where(IntegrationExchangeLog.operation_key == operation_key))
    payload_hash = _payload_hash(payload)
    if log is None:
        log = IntegrationExchangeLog(
            direction="outbound",
            operation_key=operation_key,
            entity_type=payload.entity_type,
            entity_internal_id=entity.id,
            external_1c_id=payload.external_1c_id,
            payload_hash=payload_hash,
            status="completed",
            payload=_payload_data(payload),
            completed_at=now,
        )
        session.add(log)
    else:
        log.external_1c_id = payload.external_1c_id
        log.payload_hash = payload_hash
        log.payload = _payload_data(payload)
        log.status = "completed"
        log.completed_at = now
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Идентификатор 1С уже связан с другим объектом") from exc
    return ImportResult(internal_id=entity.id)