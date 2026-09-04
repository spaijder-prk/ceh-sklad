from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models  # noqa: F401
from .config import settings
from .db import Base, engine, get_session
from .models import Product, Representative, Warehouse
from .schemas import (
    IssueRequest,
    OperationResult,
    PaymentRequest,
    ProductCreate,
    ProductRead,
    ReceiptRequest,
    RepresentativeBalanceLine,
    RepresentativeCreate,
    RepresentativeDebt,
    RepresentativeRead,
    ReturnRequest,
    SaleRequest,
    TransferRequest,
    WarehouseBalanceLine,
    WarehouseCreate,
    WarehouseRead,
)
from .services import (
    ConflictError,
    NotFoundError,
    issue_to_representative,
    receive_goods,
    register_payment,
    register_sale,
    representative_balances,
    representative_debt,
    return_from_representative,
    transfer_between_warehouses,
    warehouse_balances,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API складского учета, движения товара и расчетов с торговыми представителями.",
    lifespan=lifespan,
)
SessionDep = Annotated[Session, Depends(get_session)]


@app.exception_handler(NotFoundError)
async def handle_not_found(_, exc: NotFoundError):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def handle_conflict(_, exc: ConflictError):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health", tags=["Система"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(f"{settings.api_prefix}/warehouses", response_model=list[WarehouseRead], tags=["Справочники"])
def list_warehouses(session: SessionDep):
    return session.scalars(select(Warehouse).order_by(Warehouse.name)).all()


@app.post(
    f"{settings.api_prefix}/warehouses",
    response_model=WarehouseRead,
    status_code=201,
    tags=["Справочники"],
)
def create_warehouse(payload: WarehouseCreate, session: SessionDep):
    warehouse = Warehouse(code=payload.code, name=payload.name)
    session.add(warehouse)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Склад с таким кодом уже существует") from exc
    session.refresh(warehouse)
    return warehouse


@app.get(
    f"{settings.api_prefix}/representatives",
    response_model=list[RepresentativeRead],
    tags=["Справочники"],
)
def list_representatives(session: SessionDep):
    return session.scalars(select(Representative).order_by(Representative.name)).all()


@app.post(
    f"{settings.api_prefix}/representatives",
    response_model=RepresentativeRead,
    status_code=201,
    tags=["Справочники"],
)
def create_representative(payload: RepresentativeCreate, session: SessionDep):
    representative = Representative(code=payload.code, name=payload.name)
    session.add(representative)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Торговый представитель с таким кодом уже существует"
        ) from exc
    session.refresh(representative)
    return representative


@app.get(f"{settings.api_prefix}/products", response_model=list[ProductRead], tags=["Справочники"])
def list_products(session: SessionDep):
    return session.scalars(select(Product).order_by(Product.name)).all()


@app.post(
    f"{settings.api_prefix}/products",
    response_model=ProductRead,
    status_code=201,
    tags=["Справочники"],
)
def create_product(payload: ProductCreate, session: SessionDep):
    product = Product(**payload.model_dump())
    session.add(product)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Товар с таким артикулом уже существует") from exc
    session.refresh(product)
    return product


@app.get(
    f"{settings.api_prefix}/balances/warehouses",
    response_model=list[WarehouseBalanceLine],
    tags=["Остатки"],
)
def get_warehouse_balances(
    session: SessionDep,
    warehouse_id: UUID | None = Query(default=None),
):
    return warehouse_balances(session, warehouse_id)


@app.get(
    f"{settings.api_prefix}/balances/representatives",
    response_model=list[RepresentativeBalanceLine],
    tags=["Остатки"],
)
def get_representative_balances(
    session: SessionDep,
    representative_id: UUID | None = Query(default=None),
):
    return representative_balances(session, representative_id)


@app.get(
    f"{settings.api_prefix}/representatives/{{representative_id}}/debt",
    response_model=RepresentativeDebt,
    tags=["Деньги"],
)
def get_representative_debt(representative_id: UUID, session: SessionDep):
    return representative_debt(session, representative_id)


@app.post(
    f"{settings.api_prefix}/operations/receipt",
    response_model=OperationResult,
    status_code=201,
    tags=["Операции"],
)
def receipt(payload: ReceiptRequest, session: SessionDep):
    return receive_goods(session, payload)


@app.post(
    f"{settings.api_prefix}/operations/issue-to-representative",
    response_model=OperationResult,
    status_code=201,
    tags=["Операции"],
)
def issue(payload: IssueRequest, session: SessionDep):
    return issue_to_representative(session, payload)


@app.post(
    f"{settings.api_prefix}/operations/warehouse-transfer",
    response_model=OperationResult,
    status_code=201,
    tags=["Операции"],
)
def transfer(payload: TransferRequest, session: SessionDep):
    return transfer_between_warehouses(session, payload)


@app.post(
    f"{settings.api_prefix}/operations/representative-return",
    response_model=OperationResult,
    status_code=201,
    tags=["Операции"],
)
def representative_return(payload: ReturnRequest, session: SessionDep):
    return return_from_representative(session, payload)


@app.post(
    f"{settings.api_prefix}/operations/sale",
    response_model=OperationResult,
    status_code=201,
    tags=["Операции"],
)
def sale(payload: SaleRequest, session: SessionDep):
    return register_sale(session, payload)


@app.post(
    f"{settings.api_prefix}/operations/payment",
    response_model=OperationResult,
    status_code=201,
    tags=["Деньги"],
)
def payment(payload: PaymentRequest, session: SessionDep):
    return register_payment(session, payload)
