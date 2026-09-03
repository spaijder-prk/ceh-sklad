from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .models import InventoryBalance, Location, Product, StockDocumentKind
from .realtime import hub
from .schemas import CashHandoverIn, OperationOut, ProductOut, RepresentativeDebtOut, SaleIn, StockItemOut, TransferIn
from .services import create_cash_handover, create_sale, create_transfer, representative_debt

router = APIRouter(prefix="/api/v1")


@router.get("/products", response_model=list[ProductOut])
async def products(session: AsyncSession = Depends(get_session)) -> list[Product]:
    return list(await session.scalars(select(Product).where(Product.is_active.is_(True)).order_by(Product.name)))


@router.get("/locations")
async def locations(session: AsyncSession = Depends(get_session)) -> list[dict[str, str]]:
    rows = list(await session.scalars(select(Location).order_by(Location.kind, Location.name)))
    return [{"id": str(row.id), "name": row.name, "kind": row.kind.value} for row in rows]


@router.get("/stocks", response_model=list[StockItemOut])
async def stocks(location_id: UUID | None = None, session: AsyncSession = Depends(get_session)) -> list[StockItemOut]:
    stmt = (
        select(InventoryBalance, Location, Product)
        .join(Location, Location.id == InventoryBalance.location_id)
        .join(Product, Product.id == InventoryBalance.product_id)
        .where(Product.is_active.is_(True))
        .order_by(Location.name, Product.name)
    )
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
async def transfer(payload: TransferIn, session: AsyncSession = Depends(get_session)) -> OperationOut:
    document = await create_transfer(
        session,
        kind=StockDocumentKind.TRANSFER,
        source_location_id=payload.source_location_id,
        destination_location_id=payload.destination_location_id,
        items=payload.items,
        comment=payload.comment,
    )
    await hub.stock_changed({payload.source_location_id, payload.destination_location_id})
    return OperationOut(id=document.id, message="Перемещение проведено")


@router.post("/stock/issue-to-representative", response_model=OperationOut)
async def issue_to_representative(payload: TransferIn, session: AsyncSession = Depends(get_session)) -> OperationOut:
    document = await create_transfer(
        session,
        kind=StockDocumentKind.ISSUE_TO_REPRESENTATIVE,
        source_location_id=payload.source_location_id,
        destination_location_id=payload.destination_location_id,
        items=payload.items,
        comment=payload.comment,
    )
    await hub.stock_changed({payload.source_location_id, payload.destination_location_id})
    return OperationOut(id=document.id, message="Товар выдан торговому представителю")


@router.post("/stock/representative-return", response_model=OperationOut)
async def representative_return(payload: TransferIn, session: AsyncSession = Depends(get_session)) -> OperationOut:
    document = await create_transfer(
        session,
        kind=StockDocumentKind.REPRESENTATIVE_RETURN,
        source_location_id=payload.source_location_id,
        destination_location_id=payload.destination_location_id,
        items=payload.items,
        comment=payload.comment,
    )
    await hub.stock_changed({payload.source_location_id, payload.destination_location_id})
    return OperationOut(id=document.id, message="Возврат принят")


@router.post("/sales", response_model=OperationOut)
async def sale(payload: SaleIn, session: AsyncSession = Depends(get_session)) -> OperationOut:
    document = await create_sale(
        session,
        representative_location_id=payload.representative_location_id,
        items=payload.items,
        price_type=payload.price_type,
        comment=payload.comment,
    )
    await hub.stock_changed({payload.representative_location_id})
    return OperationOut(id=document.id, message="Продажа проведена")


@router.post("/cash-handovers", response_model=OperationOut)
async def cash_handover(payload: CashHandoverIn, session: AsyncSession = Depends(get_session)) -> OperationOut:
    transaction = await create_cash_handover(
        session,
        representative_location_id=payload.representative_location_id,
        amount=payload.amount,
        comment=payload.comment,
    )
    return OperationOut(id=transaction.id, message="Сдача денежных средств проведена")


@router.get("/representatives/{representative_location_id}/debt", response_model=RepresentativeDebtOut)
async def debt(representative_location_id: UUID, session: AsyncSession = Depends(get_session)) -> RepresentativeDebtOut:
    value: Decimal = await representative_debt(session, representative_location_id)
    return RepresentativeDebtOut(representative_location_id=representative_location_id, debt=value)


@router.websocket("/realtime")
async def realtime(websocket: WebSocket, location_id: UUID | None = None) -> None:
    await hub.connect(websocket, location_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
