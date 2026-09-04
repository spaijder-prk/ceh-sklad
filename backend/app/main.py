from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models  # noqa: F401
from .config import settings
from .db import Base, engine, get_session
from .models import Product, Representative, User, UserRole, Warehouse
from .schemas import (
    BootstrapAdminRequest,
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
    TokenResponse,
    TransferRequest,
    UserCreate,
    UserRead,
    WarehouseBalanceLine,
    WarehouseCreate,
    WarehouseRead,
)
from .security import (
    authenticate_user,
    create_access_token,
    get_current_user,
    hash_password,
    normalize_email,
    require_roles,
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
    version="0.2.0",
    description="API складского учета, движения товара и расчетов с торговыми представителями.",
    lifespan=lifespan,
)
SessionDep = Annotated[Session, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
AdminDep = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
AdminOrRepresentativeDep = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.REPRESENTATIVE))
]


@app.exception_handler(NotFoundError)
async def handle_not_found(_, exc: NotFoundError):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def handle_conflict(_, exc: ConflictError):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=409, content={"detail": str(exc)})


def representative_for_user(session: Session, user: User) -> Representative:
    representative = session.scalar(select(Representative).where(Representative.user_id == user.id))
    if representative is None:
        raise HTTPException(
            status_code=403,
            detail="Учетная запись не привязана к торговому представителю",
        )
    return representative


def ensure_representative_scope(session: Session, user: User, representative_id: UUID) -> None:
    if user.role == UserRole.REPRESENTATIVE:
        own_representative = representative_for_user(session, user)
        if own_representative.id != representative_id:
            raise HTTPException(status_code=403, detail="Нет доступа к другому торговому представителю")


@app.get("/health", tags=["Система"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    f"{settings.api_prefix}/auth/bootstrap",
    response_model=UserRead,
    status_code=201,
    tags=["Авторизация"],
)
def bootstrap_admin(payload: BootstrapAdminRequest, session: SessionDep):
    if session.scalar(select(User.id).limit(1)) is not None:
        raise HTTPException(status_code=409, detail="Первый администратор уже создан")

    user = User(
        email=normalize_email(payload.email),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.ADMIN,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Пользователь уже существует") from exc
    session.refresh(user)
    return user


@app.post(
    f"{settings.api_prefix}/auth/token",
    response_model=TokenResponse,
    tags=["Авторизация"],
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep):
    user = authenticate_user(session, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(user))


@app.get(f"{settings.api_prefix}/auth/me", response_model=UserRead, tags=["Авторизация"])
def current_user(user: CurrentUserDep):
    return user


@app.get(f"{settings.api_prefix}/users", response_model=list[UserRead], tags=["Пользователи"])
def list_users(_: AdminDep, session: SessionDep):
    return session.scalars(select(User).order_by(User.full_name)).all()


@app.post(
    f"{settings.api_prefix}/users",
    response_model=UserRead,
    status_code=201,
    tags=["Пользователи"],
)
def create_user(payload: UserCreate, _: AdminDep, session: SessionDep):
    user = User(
        email=normalize_email(payload.email),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует") from exc
    session.refresh(user)
    return user


@app.get(f"{settings.api_prefix}/warehouses", response_model=list[WarehouseRead], tags=["Справочники"])
def list_warehouses(_: CurrentUserDep, session: SessionDep):
    return session.scalars(select(Warehouse).order_by(Warehouse.name)).all()


@app.post(
    f"{settings.api_prefix}/warehouses",
    response_model=WarehouseRead,
    status_code=201,
    tags=["Справочники"],
)
def create_warehouse(payload: WarehouseCreate, _: AdminDep, session: SessionDep):
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
def list_representatives(user: CurrentUserDep, session: SessionDep):
    statement = select(Representative).order_by(Representative.name)
    if user.role == UserRole.REPRESENTATIVE:
        statement = statement.where(Representative.user_id == user.id)
    return session.scalars(statement).all()


@app.post(
    f"{settings.api_prefix}/representatives",
    response_model=RepresentativeRead,
    status_code=201,
    tags=["Справочники"],
)
def create_representative(payload: RepresentativeCreate, _: AdminDep, session: SessionDep):
    if payload.user_id is not None:
        linked_user = session.get(User, payload.user_id)
        if linked_user is None:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        if linked_user.role != UserRole.REPRESENTATIVE:
            raise HTTPException(
                status_code=409,
                detail="К представителю можно привязать только пользователя с ролью representative",
            )

    representative = Representative(**payload.model_dump())
    session.add(representative)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Код представителя или пользователь уже привязан",
        ) from exc
    session.refresh(representative)
    return representative


@app.get(f"{settings.api_prefix}/products", response_model=list[ProductRead], tags=["Справочники"])
def list_products(_: CurrentUserDep, session: SessionDep):
    return session.scalars(select(Product).order_by(Product.name)).all()


@app.post(
    f"{settings.api_prefix}/products",
    response_model=ProductRead,
    status_code=201,
    tags=["Справочники"],
)
def create_product(payload: ProductCreate, _: AdminDep, session: SessionDep):
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
    _: CurrentUserDep,
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
    user: CurrentUserDep,
    session: SessionDep,
    representative_id: UUID | None = Query(default=None),
):
    if user.role == UserRole.REPRESENTATIVE:
        own_representative = representative_for_user(session, user)
        if representative_id is not None and representative_id != own_representative.id:
            raise HTTPException(status_code=403, detail="Нет доступа к чужим остаткам")
        representative_id = own_representative.id
    return representative_balances(session, representative_id)


@app.get(
    f"{settings.api_prefix}/representatives/{{representative_id}}/debt",
    response_model=RepresentativeDebt,
    tags=["Деньги"],
)
def get_representative_debt(
    representative_id: UUID,
    user: CurrentUserDep,
    session: SessionDep,
):
    ensure_representative_scope(session, user, representative_id)
    return representative_debt(session, representative_id)


@app.post(
    f"{settings.api_prefix}/operations/receipt",
    response_model=OperationResult,
    status_code=201,
    tags=["Операции"],
)
def receipt(payload: ReceiptRequest, _: AdminDep, session: SessionDep):
    return receive_goods(session, payload)


@app.post(
    f"{settings.api_prefix}/operations/issue-to-representative",
    response_model=OperationResult,
    status_code=201,
    tags=["Операции"],
)
def issue(payload: IssueRequest, _: AdminDep, session: SessionDep):
    return issue_to_representative(session, payload)


@app.post(
    f"{settings.api_prefix}/operations/warehouse-transfer",
    response_model=OperationResult,
    status_code=201,
    tags=["Операции"],
)
def transfer(payload: TransferRequest, _: AdminDep, session: SessionDep):
    return transfer_between_warehouses(session, payload)


@app.post(
    f"{settings.api_prefix}/operations/representative-return",
    response_model=OperationResult,
    status_code=201,
    tags=["Операции"],
)
def representative_return(
    payload: ReturnRequest,
    user: AdminOrRepresentativeDep,
    session: SessionDep,
):
    ensure_representative_scope(session, user, payload.representative_id)
    return return_from_representative(session, payload)


@app.post(
    f"{settings.api_prefix}/operations/sale",
    response_model=OperationResult,
    status_code=201,
    tags=["Операции"],
)
def sale(payload: SaleRequest, user: AdminOrRepresentativeDep, session: SessionDep):
    ensure_representative_scope(session, user, payload.representative_id)
    return register_sale(session, payload)


@app.post(
    f"{settings.api_prefix}/operations/payment",
    response_model=OperationResult,
    status_code=201,
    tags=["Деньги"],
)
def payment(payload: PaymentRequest, _: AdminDep, session: SessionDep):
    return register_payment(session, payload)
