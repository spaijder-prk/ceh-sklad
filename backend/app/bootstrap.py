from sqlalchemy import select

from .auth import hash_password
from .config import settings
from .database import SessionFactory
from .models import User, UserRole


async def ensure_bootstrap_admin() -> None:
    if not settings.bootstrap_admin_login or not settings.bootstrap_admin_password:
        return
    async with SessionFactory() as session:
        existing = await session.scalar(select(User).where(User.login == settings.bootstrap_admin_login))
        if existing is not None:
            return
        session.add(
            User(
                name="Администратор",
                login=settings.bootstrap_admin_login,
                password_hash=hash_password(settings.bootstrap_admin_password),
                role=UserRole.ADMIN,
            )
        )
        await session.commit()
