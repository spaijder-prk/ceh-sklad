from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from .db import get_session
from .document_schemas import DocumentCancelResult, DocumentRead
from .document_service import cancel_document, document_journal
from .models import User, UserRole
from .money_api import router as money_router
from .realtime import stock_updates
from .reports_api import router as reports_router
from .security import require_roles


router = APIRouter(tags=["Документы"])
SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
AdminOrManagerDep = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))
]


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(
    _: AdminOrManagerDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=200),
):
    return document_journal(session, limit)


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
# собираем рядом управленческие маршруты, не раздувая основной модуль приложения.
router.include_router(reports_router)
router.include_router(money_router)
