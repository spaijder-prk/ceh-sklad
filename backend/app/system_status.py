from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import require_roles
from .config import settings
from .database import get_session
from .models import (
    IntegrationExchangeLog,
    Location,
    LocationKind,
    MoneyTransaction,
    MoneyTransactionKind,
    Product,
    StockDocument,
    User,
    UserRole,
)

router = APIRouter(prefix="/api/v1", tags=["Состояние системы"])


class SystemStatusOut(BaseModel):
    schema_revision: str
    active_users: int
    active_products: int
    active_warehouses: int
    active_representatives: int
    temporarily_locked_users: int
    integration_1c_configured: bool
    pending_1c_stock_documents: int
    pending_1c_cash_handovers: int
    failed_1c_last_24h: int
    oldest_pending_1c_at: datetime | None


async def _count(session: AsyncSession, statement) -> int:
    value = await session.scalar(statement)
    return int(value or 0)


@router.get("/system/status", response_model=SystemStatusOut)
async def system_status(
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> SystemStatusOut:
    now = datetime.now(UTC)
    day_ago = now - timedelta(hours=24)

    active_users = await _count(session, select(func.count(User.id)).where(User.is_active.is_(True)))
    active_products = await _count(session, select(func.count(Product.id)).where(Product.is_active.is_(True)))
    active_warehouses = await _count(
        session,
        select(func.count(Location.id)).where(
            Location.is_active.is_(True),
            Location.kind == LocationKind.WAREHOUSE,
        ),
    )
    active_representatives = await _count(
        session,
        select(func.count(Location.id)).where(
            Location.is_active.is_(True),
            Location.kind == LocationKind.REPRESENTATIVE,
        ),
    )
    temporarily_locked_users = await _count(
        session,
        select(func.count(User.id)).where(User.login_locked_until.is_not(None), User.login_locked_until > now),
    )

    pending_document_filter = (
        StockDocument.synced_1c_at.is_(None),
        StockDocument.external_1c_id.is_(None),
    )
    pending_cash_filter = (
        MoneyTransaction.kind == MoneyTransactionKind.CASH_HANDOVER,
        MoneyTransaction.synced_1c_at.is_(None),
        MoneyTransaction.external_1c_id.is_(None),
    )
    pending_1c_stock_documents = await _count(
        session,
        select(func.count(StockDocument.id)).where(*pending_document_filter),
    )
    pending_1c_cash_handovers = await _count(
        session,
        select(func.count(MoneyTransaction.id)).where(*pending_cash_filter),
    )
    failed_1c_last_24h = await _count(
        session,
        select(func.count(IntegrationExchangeLog.id)).where(
            IntegrationExchangeLog.status == "failed",
            IntegrationExchangeLog.created_at >= day_ago,
        ),
    )
    oldest_document = await session.scalar(select(func.min(StockDocument.created_at)).where(*pending_document_filter))
    oldest_cash = await session.scalar(select(func.min(MoneyTransaction.created_at)).where(*pending_cash_filter))
    pending_dates = [value for value in (oldest_document, oldest_cash) if value is not None]
    oldest_pending = min(pending_dates) if pending_dates else None

    revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
    return SystemStatusOut(
        schema_revision=str(revision or "unknown"),
        active_users=active_users,
        active_products=active_products,
        active_warehouses=active_warehouses,
        active_representatives=active_representatives,
        temporarily_locked_users=temporarily_locked_users,
        integration_1c_configured=bool(settings.integration_1c_api_key),
        pending_1c_stock_documents=pending_1c_stock_documents,
        pending_1c_cash_handovers=pending_1c_cash_handovers,
        failed_1c_last_24h=failed_1c_last_24h,
        oldest_pending_1c_at=oldest_pending,
    )
