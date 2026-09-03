from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auth import hash_password
from app.database import SessionFactory
from app.main import app
from app.models import User, UserRole


async def _create_user(login: str, password: str) -> None:
    async with SessionFactory() as session:
        session.add(
            User(
                name=f"Пользователь {login}",
                login=login,
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
            )
        )
        await session.commit()


async def test_login_locks_account_after_five_failures_and_unlocks_after_timeout():
    await _create_user("lock-user", "SecurePass123")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(4):
            response = await client.post(
                "/api/v1/auth/login",
                json={"login": "lock-user", "password": "WrongPass999"},
            )
            assert response.status_code == 401

        fifth = await client.post(
            "/api/v1/auth/login",
            json={"login": "lock-user", "password": "WrongPass999"},
        )
        locked_correct = await client.post(
            "/api/v1/auth/login",
            json={"login": "lock-user", "password": "SecurePass123"},
        )

    assert fifth.status_code == 429
    assert locked_correct.status_code == 429

    async with SessionFactory() as session:
        user = await session.scalar(select(User).where(User.login == "lock-user"))
        assert user is not None
        assert user.failed_login_attempts == 0
        assert user.login_locked_until is not None and user.login_locked_until > datetime.now(UTC)
        user.login_locked_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unlocked = await client.post(
            "/api/v1/auth/login",
            json={"login": "lock-user", "password": "SecurePass123"},
        )
    assert unlocked.status_code == 200

    async with SessionFactory() as session:
        user = await session.scalar(select(User).where(User.login == "lock-user"))
        assert user is not None
        assert user.failed_login_attempts == 0
        assert user.login_locked_until is None


async def test_successful_login_resets_failed_attempt_counter():
    await _create_user("reset-counter", "SecurePass123")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(2):
            assert (
                await client.post(
                    "/api/v1/auth/login",
                    json={"login": "reset-counter", "password": "WrongPass999"},
                )
            ).status_code == 401
        successful = await client.post(
            "/api/v1/auth/login",
            json={"login": "reset-counter", "password": "SecurePass123"},
        )

    assert successful.status_code == 200
    async with SessionFactory() as session:
        user = await session.scalar(select(User).where(User.login == "reset-counter"))
        assert user is not None
        assert user.failed_login_attempts == 0
        assert user.login_locked_until is None


async def test_unknown_login_uses_generic_authentication_error():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"login": "unknown-user", "password": "AnyPassword123"},
        )
    assert response.status_code == 401
    assert response.json()["detail"] == "Неверный логин или пароль"
