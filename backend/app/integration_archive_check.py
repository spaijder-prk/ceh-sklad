from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .integration_1c import require_1c_key
from .models import IntegrationExchangeLog, InventoryBalance, Product


router = APIRouter(
    prefix="/api/v1/integration/1c",
    tags=["Интеграция 1С"],
    dependencies=[Depends(require_1c_key)],
)


class ProductArchiveCheck(BaseModel):
    exists: bool
    internal_id: UUID | None = None
    is_active: bool | None = None
    total_stock: Decimal = Decimal("0")
    can_archive: bool = False
    reason: str | None = None


class ArchiveProductIn(BaseModel):
    operation_key: str = Field(min_length=8, max_length=120)


class ArchiveProductResult(BaseModel):
    internal_id: UUID
    repeated: bool = False


def _archive_payload_hash(external_1c_id: str) -> str:
    return hashlib.sha256(f"product_archive:{external_1c_id}".encode("utf-8")).hexdigest()


async def _total_stock(session: AsyncSession, product_id: UUID) -> Decimal:
    value = await session.scalar(
        select(func.coalesce(func.sum(InventoryBalance.quantity), 0)).where(
            InventoryBalance.product_id == product_id
        )
    )
    return Decimal(value)


@router.get("/products/{external_1c_id}/archive-check", response_model=ProductArchiveCheck)
async def product_archive_check(
    external_1c_id: str,
    session: AsyncSession = Depends(get_session),
) -> ProductArchiveCheck:
    """Read-only precheck перед автоматической архивацией товара из УНФ."""
    product = await session.scalar(
        select(Product).where(Product.external_1c_id == external_1c_id)
    )
    if product is None:
        return ProductArchiveCheck(
            exists=False,
            reason="Товар с таким external_1c_id отсутствует в ceh-sklad",
        )

    total_stock = await _total_stock(session, product.id)
    if not product.is_active:
        return ProductArchiveCheck(
            exists=True,
            internal_id=product.id,
            is_active=False,
            total_stock=total_stock,
            can_archive=total_stock == 0,
            reason="Товар уже архивирован" if total_stock == 0 else "Архивный товар имеет ненулевой остаток",
        )

    if total_stock != 0:
        return ProductArchiveCheck(
            exists=True,
            internal_id=product.id,
            is_active=True,
            total_stock=total_stock,
            can_archive=False,
            reason=f"Нельзя архивировать товар с ненулевым остатком {total_stock}",
        )

    return ProductArchiveCheck(
        exists=True,
        internal_id=product.id,
        is_active=True,
        total_stock=total_stock,
        can_archive=True,
    )


@router.post("/products/{external_1c_id}/archive", response_model=ArchiveProductResult)
async def archive_product(
    external_1c_id: str,
    payload: ArchiveProductIn,
    session: AsyncSession = Depends(get_session),
) -> ArchiveProductResult:
    """Атомарно архивирует товар с нулевым остатком и идемпотентным operation key."""
    payload_hash = _archive_payload_hash(external_1c_id)
    log = await session.scalar(
        select(IntegrationExchangeLog)
        .where(IntegrationExchangeLog.operation_key == payload.operation_key)
        .with_for_update()
    )
    if log is not None:
        if (
            log.entity_type != "product_archive"
            or log.external_1c_id != external_1c_id
            or log.payload_hash != payload_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ключ операции архивирования уже использован с другим содержимым",
            )
        if log.status == "completed" and log.entity_internal_id is not None:
            return ArchiveProductResult(internal_id=log.entity_internal_id, repeated=True)
        if log.status == "processing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Операция архивирования уже выполняется",
            )
        log.status = "processing"
        log.error_message = None
        log.completed_at = None
    else:
        log = IntegrationExchangeLog(
            direction="inbound",
            operation_key=payload.operation_key,
            entity_type="product_archive",
            external_1c_id=external_1c_id,
            payload_hash=payload_hash,
            status="processing",
            payload={"external_1c_id": external_1c_id, "action": "archive"},
        )
        session.add(log)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Операция архивирования выполняется параллельно",
            ) from exc

    product = await session.scalar(
        select(Product)
        .where(Product.external_1c_id == external_1c_id)
        .with_for_update()
    )
    if product is None:
        log.status = "failed"
        log.error_message = "Товар с таким external_1c_id отсутствует в ceh-sklad"
        log.completed_at = datetime.now(UTC)
        await session.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=log.error_message)

    if not product.is_active:
        log.status = "completed"
        log.entity_internal_id = product.id
        log.completed_at = datetime.now(UTC)
        await session.commit()
        return ArchiveProductResult(internal_id=product.id, repeated=True)

    total_stock = await _total_stock(session, product.id)
    if total_stock != 0:
        message = f"Нельзя архивировать товар с ненулевым остатком {total_stock}"
        log.status = "failed"
        log.entity_internal_id = product.id
        log.error_message = message
        log.completed_at = datetime.now(UTC)
        await session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)

    product.is_active = False
    log.status = "completed"
    log.entity_internal_id = product.id
    log.error_message = None
    log.completed_at = datetime.now(UTC)
    await session.commit()
    return ArchiveProductResult(internal_id=product.id, repeated=False)
