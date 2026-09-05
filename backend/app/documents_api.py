from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .document_schemas import DocumentCancelResult, DocumentRead
from .document_service import cancel_document, document_journal
from .integration_api import router as integration_router
from .models import Representative, User, UserRole
from .money_api import router as money_router
from .money_schemas import MoneyPostingRead
from .money_service import money_journal
from .realtime import stock_updates
from .realtime_api import router as realtime_router
from .reports_api import router as reports_router
from .security import require_roles
from .users_api import router as users_router


router = APIRouter(tags=["Документы"])
SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
AdminOrManagerDep = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))
]
RepresentativeDep = Annotated[
    User, Depends(require_roles(UserRole.REPRESENTATIVE))
]


def representative_for_user(session: Session, user: User) -> Representative:
    representative = session.scalar(
        select(Representative).where(Representative.user_id == user.id)
    )
    if representative is None:
        raise HTTPException(
            status_code=403,
            detail="Учетная запись не привязана к торговому представителю",
        )
    return representative


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(
    _: AdminOrManagerDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=200),
):
    return document_journal(session, limit)


@router.get("/my/documents", response_model=list[DocumentRead])
def list_my_documents(
    user: RepresentativeDep,
    session: SessionDep,
    limit: int = Query(default=30, ge=1, le=100),
):
    representative = representative_for_user(session, user)
    return document_journal(session, limit, representative.id)


@router.get("/my/money-postings", response_model=list[MoneyPostingRead])
def list_my_money_postings(
    user: RepresentativeDep,
    session: SessionDep,
    limit: int = Query(default=30, ge=1, le=100),
):
    representative = representative_for_user(session, user)
    return money_journal(session, limit, representative.id)


@router.post(
    "/documents/{document_id}/cancel",
    response_model=DocumentCancelResult,
)
def cancel_document_route(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    _: AdminDep,
    session: SessionDep,
):
    result = cancel_document(session, document_id)
    if result.stock_changed or result.debt_changed:
        background_tasks.add_task(
            stock_updates.broadcast,
            {
                "type": "state_changed",
                "stock_changed": result.stock_changed,
                "debt_changed": result.debt_changed,
                "document_id": str(result.document_id),
                "money_posting_id": None,
            },
        )
    return result


# Main подключает этот подмаршрутизатор под общим /api/v1, поэтому здесь
# собираем дополнительные контуры API, не раздувая основной модуль приложения.
router.include_router(reports_router)
router.include_router(money_router)
router.include_router(integration_router)
router.include_router(realtime_router)
router.include_router(users_router)
