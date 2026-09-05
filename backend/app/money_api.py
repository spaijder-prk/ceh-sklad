from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from .db import get_session
from .models import User, UserRole
from .money_schemas import MoneyPostingRead, PaymentReverseResult
from .money_service import money_journal, reverse_payment
from .realtime import stock_updates
from .security import require_roles


router = APIRouter(prefix="/money-postings", tags=["Деньги"])
SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
AdminOrManagerDep = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))
]


@router.get("", response_model=list[MoneyPostingRead])
def list_money_postings(
    _: AdminOrManagerDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=200),
):
    return money_journal(session, limit)


@router.post("/{posting_id}/reverse", response_model=PaymentReverseResult)
def reverse_payment_route(
    posting_id: UUID,
    background_tasks: BackgroundTasks,
    _: AdminDep,
    session: SessionDep,
):
    result = reverse_payment(session, posting_id)
    if not result.already_reversed:
        background_tasks.add_task(
            stock_updates.broadcast,
            {
                "type": "state_changed",
                "stock_changed": False,
                "debt_changed": True,
                "document_id": None,
                "money_posting_id": str(result.reversal_id),
            },
        )
    return result
