from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user, hash_password, require_roles, validate_new_password, verify_password
from .database import get_session
from .models import User, UserRole

router = APIRouter(prefix="/api/v1", tags=["Безопасность учетной записи"])


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=10, max_length=128)


class PasswordOperationOut(BaseModel):
    message: str


@router.post("/auth/change-password", response_model=PasswordOperationOut)
async def change_password(
    payload: ChangePasswordIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PasswordOperationOut:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Текущий пароль указан неверно",
        )
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Новый пароль должен отличаться от текущего",
        )
    validate_new_password(payload.new_password, user.login)
    user.password_hash = hash_password(payload.new_password)
    await session.commit()
    return PasswordOperationOut(message="Пароль изменен. Все ранее выданные сессии недействительны")


@router.post("/admin/users/{user_id}/reset-password", response_model=PasswordOperationOut)
async def reset_user_password(
    user_id: UUID,
    payload: ResetPasswordIn,
    _: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> PasswordOperationOut:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    validate_new_password(payload.new_password, user.login)
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Новый пароль должен отличаться от текущего",
        )
    user.password_hash = hash_password(payload.new_password)
    await session.commit()
    return PasswordOperationOut(message="Пароль пользователя сброшен. Все его старые сессии недействительны")
