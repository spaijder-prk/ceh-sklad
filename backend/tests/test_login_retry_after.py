from httpx import ASGITransport, AsyncClient

from app.auth import hash_password
from app.database import SessionFactory
from app.main import app
from app.models import User, UserRole


async def test_login_lock_returns_dynamic_retry_after_header():
    async with SessionFactory() as session:
        user = User(
            name="Retry After",
            login="retry-after-user",
            password_hash=hash_password("CorrectPass123"),
            role=UserRole.ADMIN,
        )
        session.add(user)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(4):
            response = await client.post(
                "/api/v1/auth/login",
                json={"login": "retry-after-user", "password": "WrongPass999"},
            )
            assert response.status_code == 401
            assert "Retry-After" not in response.headers

        locked = await client.post(
            "/api/v1/auth/login",
            json={"login": "retry-after-user", "password": "WrongPass999"},
        )
        assert locked.status_code == 429
        first_retry = int(locked.headers["Retry-After"])
        assert 1 <= first_retry <= 300

        still_locked = await client.post(
            "/api/v1/auth/login",
            json={"login": "retry-after-user", "password": "CorrectPass123"},
        )
        assert still_locked.status_code == 429
        second_retry = int(still_locked.headers["Retry-After"])
        assert 1 <= second_retry <= first_retry


async def test_login_validation_error_is_not_given_retry_after():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invalid = await client.post("/api/v1/auth/login", json={"login": ""})

    assert invalid.status_code == 422
    assert "Retry-After" not in invalid.headers
