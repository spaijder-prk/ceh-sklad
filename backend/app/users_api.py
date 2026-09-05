from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .models import User, UserRole
from .security import hash_password, require_roles


router = APIRouter(tags=["Пользователи"])
SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


class UserAccessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool


class UserAccessUpdate(BaseModel):
    is_active: bool | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_changes(self):
        if self.is_active is None and self.new_password is None:
            raise ValueError("Необходимо изменить статус или задать новый пароль")
        return self


@router.get("/users/access", response_model=list[UserAccessRead])
def list_user_access(_: AdminDep, session: SessionDep):
    return session.scalars(select(User).order_by(User.full_name, User.email)).all()


@router.patch("/users/{user_id}/access", response_model=UserAccessRead)
def update_user_access(
    user_id: UUID,
    payload: UserAccessUpdate,
    admin: AdminDep,
    session: SessionDep,
):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if user.id == admin.id and payload.is_active is False:
        raise HTTPException(
            status_code=409,
            detail="Нельзя отключить собственную учетную запись администратора",
        )

    invalidate_tokens = False
    if payload.new_password is not None:
        user.password_hash = hash_password(payload.new_password)
        invalidate_tokens = True

    if payload.is_active is not None and payload.is_active != user.is_active:
        if payload.is_active is False:
            invalidate_tokens = True
        user.is_active = payload.is_active

    if invalidate_tokens:
        user.auth_version = int(user.auth_version or 1) + 1

    session.commit()
    session.refresh(user)
    return user
