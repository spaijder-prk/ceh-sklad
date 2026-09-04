from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .integration_1c import require_1c_key
from .models import InventoryBalance, Product


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

    value = await session.scalar(
        select(func.coalesce(func.sum(InventoryBalance.quantity), 0)).where(
            InventoryBalance.product_id == product.id
        )
    )
    total_stock = Decimal(value)
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
