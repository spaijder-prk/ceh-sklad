from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import require_roles
from .database import get_session
from .models import User, UserRole

router = APIRouter(prefix="/api/v1/admin", tags=["Управление пользователями"])


class ManagedUserOut(BaseModel):
    id: UUID
    name: str
    login: str
    role: str
    location_id: UUID | None
    is_active: bool


class UserStatusIn(BaseModel):
    is_active: bool


def _managed_user(user: User) -> ManagedUserOut:
    return ManagedUserOut(
        id=user.id,
        name=user.name,
        login=user.login,
        role=user.role.value,
        location_id=user.location_id,
        is_active=user.is_active,
    )


@router.get("/managed-users", response_model=list[ManagedUserOut])
async def managed_users(
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> list[ManagedUserOut]:
    rows = list(await session.scalars(select(User).order_by(User.name, User.login)))
    return [_managed_user(row) for row in rows]


@router.patch("/users/{user_id}/status", response_model=ManagedUserOut)
async def set_user_status(
    user_id: UUID,
    payload: UserStatusIn,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> ManagedUserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if user.id == current_user.id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Нельзя заблокировать собственную учетную запись",
        )
    user.is_active = payload.is_active
    await session.commit()
    await session.refresh(user)
    return _managed_user(user)
