import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import get_session
from .models import User, UserRole

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def validate_new_password(password: str, login: str | None = None) -> None:
    if len(password) < 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Пароль должен содержать не менее 10 символов",
        )
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Пароль должен содержать буквы и цифры",
        )
    if login and password.casefold() == login.casefold():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Пароль не должен совпадать с логином",
        )
    if password.casefold() in {"password123", "qwerty12345", "admin12345", "1234567890"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Выберите менее предсказуемый пароль",
        )


def _password_fingerprint(encoded: str) -> str:
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "pwd": _password_fingerprint(user.password_hash),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token_identity(token: str) -> tuple[UUID, str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        fingerprint = payload["pwd"]
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ValueError("Некорректный отпечаток сессии")
        return UUID(payload["sub"]), fingerprint
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен") from exc


def decode_user_id(token: str) -> UUID:
    return decode_token_identity(token)[0]


def token_matches_user(token: str, user: User) -> bool:
    user_id, fingerprint = decode_token_identity(token)
    return user_id == user.id and hmac.compare_digest(fingerprint, _password_fingerprint(user.password_hash))


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    user_id, fingerprint = decode_token_identity(credentials.credentials)
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь недоступен")
    if not hmac.compare_digest(fingerprint, _password_fingerprint(user.password_hash)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия устарела. Войдите снова")
    return user


def require_roles(*roles: UserRole):
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return user

    return dependency
