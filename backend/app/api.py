from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import create_access_token, decode_user_id, get_current_user, require_roles, verify_password
from .database import SessionFactory, get_session
from .models import InventoryBalance, Location, LocationKind, Product, StockDocumentKind, User, UserRole
from .realtime import hub
from .schemas import CashHandoverIn, LoginIn, OperationOut, ProductOut, RepresentativeDebtOut, SaleIn, StockItemOut, TokenOut, TransferIn, UserOut
from .services import create_cash_handover, create_sale, create_transfer, representative_debt

router = APIRouter(prefix="/api/v1")


def _ensure_own_location(user: User, location_id: UUID) -> None:
    if user.role == UserRole.REPRESENTATIVE and user.location_id != location_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Операция доступна только для собственного остатка")


@router.post("/auth/login", response_model=TokenOut)
async def login(payload: LoginIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    user = await session.scalar(select(User).where(User.login == payload.login))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")
    return TokenOut(access_token=create_access_token(user))


@router.get("/auth/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(id=user.id, name=user.name, login=user.login, role=user.role.value, location_id=user.location_id)


@router.get("/products", response_model=list[ProductOut])
async def products(_: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[Product]:
    return list(await session.scalars(select(Product).where(Product.is_active.is_(True)).order_by(Product.name)))


@router.get("/locations")
async def locations(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[dict[str, str]]:
    stmt = select(Location).order_by(Location.kind, Location.name)
    if user.role == UserRole.REPRESENTATIVE:
        stmt = stmt.where(or_(Location.kind == LocationKind.WAREHOUSE, Location.id == user.location_id))
    rows = list(await session.scalars(stmt))
    return [{"id": str(row.id), "name": row.name, "kind": row.kind.value} for row in rows]


@router.get("/stocks", response_model=list[StockItemOut])
async def stocks(location_id: UUID | None = None, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[StockItemOut]:
    stmt = (
        select(InventoryBalance, Location, Product)
        .join(Location, Location.id == InventoryBalance.location_id)
        .join(Product, Product.id == InventoryBalance.product_id)
        .where(Product.is_active.is_(True))
        .order_by(Location.name, Product.name)
    )
    if user.role == UserRole.REPRESENTATIVE:
        stmt = stmt.where(or_(Location.kind == LocationKind.WAREHOUSE, Location.id == user.location_id))
    if location_id:
        stmt = stmt.where(InventoryBalance.location_id == location_id)
    rows = (await session.execute(stmt)).all()
    return [
        StockItemOut(
            location_id=balance.location_id,
            location_name=location.name,
            product_id=product.id,
            sku=product.sku,
            product_name=product.name,
            unit_name=product.unit_name,
            quantity=balance.quantity,
            retail_price=product.retail_price,
            wholesale_price=product.wholesale_price,
        )
        for balance, location, product in rows
    ]


@router.post("/stock/transfers", response_model=OperationOut)
async def transfer(payload: TransferIn, user: User = Depends(require_roles(UserRole.ADMIN)), session: AsyncSession = Depends(get_session)) -> OperationOut:
    document = await create_transfer(session, kind=StockDocumentKind.TRANSFER, source_location_id=payload.source_location_id, destination_location_id=payload.destination_location_id, items=payload.items, comment=payload.comment, created_by_id=user.id)
    await hub.stock_changed({payload.source_location_id, payload.destination_location_id})
    return OperationOut(id=document.id, message="Перемещение проведено")


@router.post("/stock/issue-to-representative", response_model=OperationOut)
async def issue_to_representative(payload: TransferIn, user: User = Depends(require_roles(UserRole.ADMIN)), session: AsyncSession = Depends(get_session)) -> OperationOut:
    document = await create_transfer(session, kind=StockDocumentKind.ISSUE_TO_REPRESENTATIVE, source_location_id=payload.source_location_id, destination_location_id=payload.destination_location_id, items=payload.items, comment=payload.comment, created_by_id=user.id)
    await hub.stock_changed({payload.source_location_id, payload.destination_location_id})
    return OperationOut(id=document.id, message="Товар выдан торговому представителю")


@router.post("/stock/representative-return", response_model=OperationOut)
async def representative_return(payload: TransferIn, user: User = Depends(require_roles(UserRole.ADMIN, UserRole.REPRESENTATIVE)), session: AsyncSession = Depends(get_session)) -> OperationOut:
    _ensure_own_location(user, payload.source_location_id)
    document = await create_transfer(session, kind=StockDocumentKind.REPRESENTATIVE_RETURN, source_location_id=payload.source_location_id, destination_location_id=payload.destination_location_id, items=payload.items, comment=payload.comment, created_by_id=user.id)
    await hub.stock_changed({payload.source_location_id, payload.destination_location_id})
    return OperationOut(id=document.id, message="Возврат принят")


@router.post("/sales", response_model=OperationOut)
async def sale(payload: SaleIn, user: User = Depends(require_roles(UserRole.ADMIN, UserRole.REPRESENTATIVE)), session: AsyncSession = Depends(get_session)) -> OperationOut:
    _ensure_own_location(user, payload.representative_location_id)
    document = await create_sale(session, representative_location_id=payload.representative_location_id, items=payload.items, price_type=payload.price_type, comment=payload.comment, created_by_id=user.id)
    await hub.stock_changed({payload.representative_location_id})
    return OperationOut(id=document.id, message="Продажа проведена")


@router.post("/cash-handovers", response_model=OperationOut)
async def cash_handover(payload: CashHandoverIn, user: User = Depends(require_roles(UserRole.ADMIN, UserRole.REPRESENTATIVE)), session: AsyncSession = Depends(get_session)) -> OperationOut:
    _ensure_own_location(user, payload.representative_location_id)
    transaction = await create_cash_handover(session, representative_location_id=payload.representative_location_id, amount=payload.amount, comment=payload.comment, created_by_id=user.id)
    return OperationOut(id=transaction.id, message="Сдача денежных средств проведена")


@router.get("/representatives/{representative_location_id}/debt", response_model=RepresentativeDebtOut)
async def debt(representative_location_id: UUID, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> RepresentativeDebtOut:
    _ensure_own_location(user, representative_location_id)
    value: Decimal = await representative_debt(session, representative_location_id)
    return RepresentativeDebtOut(representative_location_id=representative_location_id, debt=value)


@router.websocket("/realtime")
async def realtime(websocket: WebSocket, token: str, location_id: UUID | None = None) -> None:
    try:
        user_id = decode_user_id(token)
        async with SessionFactory() as session:
            user = await session.get(User, user_id)
            if user is None or not user.is_active:
                await websocket.close(code=4401)
                return
            if user.role == UserRole.REPRESENTATIVE and location_id not in (None, user.location_id):
                await websocket.close(code=4403)
                return
        await hub.connect(websocket, location_id)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
    except HTTPException:
        await websocket.close(code=4401)
