from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .db import get_session
from .models import User, UserRole
from .report_schemas import ReportSummary, RepresentativeReportLine
from .report_service import report_summary, representative_report
from .security import require_roles


router = APIRouter(prefix="/reports", tags=["Отчеты"])
SessionDep = Annotated[Session, Depends(get_session)]
AdminOrManagerDep = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))
]


@router.get("/summary", response_model=ReportSummary)
def get_report_summary(
    _: AdminOrManagerDep,
    session: SessionDep,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
):
    try:
        return report_summary(session, date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/representatives", response_model=list[RepresentativeReportLine])
def get_representative_report(
    _: AdminOrManagerDep,
    session: SessionDep,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
):
    try:
        return representative_report(session, date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
