from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_session
from .models import StockDocument, User, UserRole

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/token")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hash.verify(password, encoded_hash)


def authenticate_user(session: Session, email: str, password: str) -> User | None:
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(user: User) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> UUID:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("token_type") == "realtime_ws":
        raise InvalidTokenError("WebSocket-ticket нельзя использовать как access token")
    return UUID(payload["sub"])


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Недействительный или просроченный токен",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_access_token(token)
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise credentials_error from exc

    user = session.get(User, user_id)
    if user is None:
        raise credentials_error
    session.info["current_user_id"] = user.id
    return user


def require_roles(*roles: UserRole):
    allowed = set(roles)

    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Недостаточно прав для выполнения операции")
        return user

    return dependency


@event.listens_for(Session, "before_flush")
def assign_document_creator(session: Session, _flush_context, _instances) -> None:
    user_id = session.info.get("current_user_id")
    if user_id is None:
        return
    for instance in session.new:
        if isinstance(instance, StockDocument) and instance.created_by_user_id is None:
            instance.created_by_user_id = user_id
