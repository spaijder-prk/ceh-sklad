from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from .config import settings
from .db import get_session
from .document_schemas import DocumentRead
from .document_service import document_journal
from .integration_models import OneCEntityType
from .integration_schemas import (
    OneCDocumentPage,
    OneCEntityLinkRead,
    OneCEntityLinkWrite,
    OneCMoneyPostingPage,
    OneCSnapshot,
)
from .integration_service import (
    build_1c_document_page,
    build_1c_money_posting_page,
    build_1c_snapshot,
    list_1c_entity_links,
    resolve_1c_entity_link,
    upsert_1c_entity_link,
)
from .money_schemas import MoneyPostingRead
from .money_service import money_journal
from .realtime import stock_updates
from .schemas import (
    IssueRequest,
    OperationResult,
    PaymentRequest,
    ReceiptRequest,
    ReturnRequest,
    SaleRequest,
    TransferRequest,
)
from .services import (
    issue_to_representative,
    receive_goods,
    register_payment,
    register_sale,
    return_from_representative,
    transfer_between_warehouses,
)


router = APIRouter(prefix="/integration/1c", tags=["Интеграция 1С"])
SessionDep = Annotated[Session, Depends(get_session)]


def require_integration_key(
    integration_key: Annotated[str | None, Header(alias="X-Integration-Key")] = None,
) -> None:
    configured_key = settings.integration_api_key
    if not configured_key:
        raise HTTPException(status_code=503, detail="Интеграция с 1С не настроена")
    if integration_key is None or not compare_digest(
        integration_key.encode("utf-8"),
        configured_key.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="Неверный ключ интеграции")


IntegrationDep = Annotated[None, Depends(require_integration_key)]


def require_external_id(payload) -> None:
    if not payload.external_id or not payload.external_id.strip():
        raise HTTPException(
            status_code=422,
            detail="Для операции обмена с 1С обязателен external_id",
        )


def publish_change(
    background_tasks: BackgroundTasks,
    result: OperationResult,
    *,
    stock_changed: bool,
    debt_changed: bool,
) -> None:
    background_tasks.add_task(
        stock_updates.broadcast,
        {
            "type": "state_changed",
            "stock_changed": stock_changed,
            "debt_changed": debt_changed,
            "document_id": str(result.document_id) if result.document_id else None,
            "money_posting_id": str(result.money_posting_id) if result.money_posting_id else None,
        },
    )


def _cursor_error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


@router.get("/snapshot", response_model=OneCSnapshot)
def snapshot(_: IntegrationDep, session: SessionDep):
    return build_1c_snapshot(session)


@router.get("/entity-links", response_model=list[OneCEntityLinkRead])
def entity_links(_: IntegrationDep, session: SessionDep):
    return list_1c_entity_links(session)


@router.put("/entity-links", response_model=OneCEntityLinkRead)
def put_entity_link(
    payload: OneCEntityLinkWrite,
    _: IntegrationDep,
    session: SessionDep,
):
    return upsert_1c_entity_link(session, payload)


@router.get("/entity-links/resolve", response_model=OneCEntityLinkRead)
def resolve_entity_link(
    _: IntegrationDep,
    session: SessionDep,
    entity_type: OneCEntityType = Query(),
    external_ref: str = Query(min_length=1, max_length=255),
):
    return resolve_1c_entity_link(session, entity_type, external_ref)


@router.get("/documents", response_model=list[DocumentRead])
def documents(
    _: IntegrationDep,
    session: SessionDep,
    limit: int = Query(default=200, ge=1, le=1000),
):
    return document_journal(session, limit=limit)


@router.get("/documents/changes", response_model=OneCDocumentPage)
def document_changes(
    _: IntegrationDep,
    session: SessionDep,
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=200, ge=1, le=1000),
):
    try:
        return build_1c_document_page(session, cursor=cursor, limit=limit)
    except ValueError as error:
        raise _cursor_error(error) from error


@router.get("/money-postings", response_model=list[MoneyPostingRead])
def money_postings(
    _: IntegrationDep,
    session: SessionDep,
    limit: int = Query(default=200, ge=1, le=1000),
):
    return money_journal(session, limit=limit)


@router.get("/money-postings/changes", response_model=OneCMoneyPostingPage)
def money_posting_changes(
    _: IntegrationDep,
    session: SessionDep,
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=200, ge=1, le=1000),
):
    try:
        return build_1c_money_posting_page(session, cursor=cursor, limit=limit)
    except ValueError as error:
        raise _cursor_error(error) from error


@router.post("/operations/receipt", response_model=OperationResult, status_code=201)
def receipt(
    payload: ReceiptRequest,
    background_tasks: BackgroundTasks,
    _: IntegrationDep,
    session: SessionDep,
):
    require_external_id(payload)
    result = receive_goods(session, payload)
    publish_change(background_tasks, result, stock_changed=True, debt_changed=False)
    return result


@router.post(
    "/operations/issue-to-representative",
    response_model=OperationResult,
    status_code=201,
)
def issue(
    payload: IssueRequest,
    background_tasks: BackgroundTasks,
    _: IntegrationDep,
    session: SessionDep,
):
    require_external_id(payload)
    result = issue_to_representative(session, payload)
    publish_change(background_tasks, result, stock_changed=True, debt_changed=False)
    return result


@router.post("/operations/warehouse-transfer", response_model=OperationResult, status_code=201)
def transfer(
    payload: TransferRequest,
    background_tasks: BackgroundTasks,
    _: IntegrationDep,
    session: SessionDep,
):
    require_external_id(payload)
    result = transfer_between_warehouses(session, payload)
    publish_change(background_tasks, result, stock_changed=True, debt_changed=False)
    return result


@router.post(
    "/operations/representative-return",
    response_model=OperationResult,
    status_code=201,
)
def representative_return(
    payload: ReturnRequest,
    background_tasks: BackgroundTasks,
    _: IntegrationDep,
    session: SessionDep,
):
    require_external_id(payload)
    result = return_from_representative(session, payload)
    publish_change(background_tasks, result, stock_changed=True, debt_changed=False)
    return result


@router.post("/operations/sale", response_model=OperationResult, status_code=201)
def sale(
    payload: SaleRequest,
    background_tasks: BackgroundTasks,
    _: IntegrationDep,
    session: SessionDep,
):
    require_external_id(payload)
    result = register_sale(session, payload)
    publish_change(background_tasks, result, stock_changed=True, debt_changed=True)
    return result


@router.post("/operations/payment", response_model=OperationResult, status_code=201)
def payment(
    payload: PaymentRequest,
    background_tasks: BackgroundTasks,
    _: IntegrationDep,
    session: SessionDep,
):
    require_external_id(payload)
    result = register_payment(session, payload)
    publish_change(background_tasks, result, stock_changed=False, debt_changed=True)
    return result
