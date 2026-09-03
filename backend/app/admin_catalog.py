from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import require_roles
from .database import get_session
from .models import InventoryBalance, Location, Product, User, UserRole

router = APIRouter(prefix="/api/v1/admin/catalog", tags=["Управление справочниками"])


class ManagedProductOut(BaseModel):
    id: UUID
    sku: str
    name: str
    unit_name: str
    retail_price: Decimal
    wholesale_price: Decimal
    external_1c_id: str | None
    is_active: bool


class ProductUpdateIn(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=2, max_length=200)
    unit_name: str | None = Field(default=None, min_length=1, max_length=30)
    retail_price: Decimal | None = Field(default=None, ge=0)
    wholesale_price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ManagedLocationOut(BaseModel):
    id: UUID
    name: str
    kind: str
    external_1c_id: str | None
    is_active: bool


class LocationUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    is_active: bool | None = None


def _product_out(product: Product) -> ManagedProductOut:
    return ManagedProductOut(
        id=product.id,
        sku=product.sku,
        name=product.name,
        unit_name=product.unit_name,
        retail_price=product.retail_price,
        wholesale_price=product.wholesale_price,
        external_1c_id=product.external_1c_id,
        is_active=product.is_active,
    )


def _location_out(location: Location) -> ManagedLocationOut:
    return ManagedLocationOut(
        id=location.id,
        name=location.name,
        kind=location.kind.value,
        external_1c_id=location.external_1c_id,
        is_active=location.is_active,
    )


async def _has_nonzero_stock(session: AsyncSession, *, location_id: UUID | None = None, product_id: UUID | None = None) -> bool:
    stmt = select(InventoryBalance.id).where(InventoryBalance.quantity != 0)
    if location_id is not None:
        stmt = stmt.where(InventoryBalance.location_id == location_id)
    if product_id is not None:
        stmt = stmt.where(InventoryBalance.product_id == product_id)
    return await session.scalar(stmt.limit(1)) is not None


@router.get("/products", response_model=list[ManagedProductOut])
async def managed_products(
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> list[ManagedProductOut]:
    rows = list(await session.scalars(select(Product).order_by(Product.name, Product.sku)))
    return [_product_out(row) for row in rows]


@router.patch("/products/{product_id}", response_model=ManagedProductOut)
async def update_product(
    product_id: UUID,
    payload: ProductUpdateIn,
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> ManagedProductOut:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")
    if payload.sku is not None and payload.sku != product.sku:
        owner = await session.scalar(select(Product).where(Product.sku == payload.sku, Product.id != product.id))
        if owner is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Артикул уже принадлежит другому товару")
        product.sku = payload.sku
    if payload.name is not None:
        product.name = payload.name
    if payload.unit_name is not None:
        product.unit_name = payload.unit_name
    if payload.retail_price is not None:
        product.retail_price = payload.retail_price
    if payload.wholesale_price is not None:
        product.wholesale_price = payload.wholesale_price
    if payload.is_active is not None and payload.is_active != product.is_active:
        if not payload.is_active and await _has_nonzero_stock(session, product_id=product.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя архивировать товар, пока по нему есть ненулевой остаток",
            )
        product.is_active = payload.is_active
    await session.commit()
    await session.refresh(product)
    return _product_out(product)


@router.get("/locations", response_model=list[ManagedLocationOut])
async def managed_locations(
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> list[ManagedLocationOut]:
    rows = list(await session.scalars(select(Location).order_by(Location.kind, Location.name)))
    return [_location_out(row) for row in rows]


@router.patch("/locations/{location_id}", response_model=ManagedLocationOut)
async def update_location(
    location_id: UUID,
    payload: LocationUpdateIn,
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> ManagedLocationOut:
    location = await session.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Место хранения не найдено")
    if payload.name is not None and payload.name != location.name:
        owner = await session.scalar(select(Location).where(Location.name == payload.name, Location.id != location.id))
        if owner is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Название уже принадлежит другому месту хранения")
        location.name = payload.name
    if payload.is_active is not None and payload.is_active != location.is_active:
        if not payload.is_active:
            if await _has_nonzero_stock(session, location_id=location.id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Нельзя архивировать место хранения с ненулевым остатком",
                )
            assigned_user = await session.scalar(
                select(User).where(User.location_id == location.id, User.is_active.is_(True)).limit(1)
            )
            if assigned_user is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Сначала заблокируйте или переназначьте активного пользователя этого места хранения",
                )
        location.is_active = payload.is_active
    await session.commit()
    await session.refresh(location)
    return _location_out(location)
