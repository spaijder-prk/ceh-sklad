from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token, hash_password
from app.main import app
from app.models import User, UserRole


async def test_admin_can_block_user_but_not_self(session):
    admin = User(
        name="Администратор",
        login="admin-status",
        password_hash=hash_password("admin-password-123"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    representative = User(
        name="Представитель",
        login="rep-status",
        password_hash=hash_password("rep-password-123"),
        role=UserRole.REPRESENTATIVE,
        is_active=True,
    )
    session.add_all([admin, representative])
    await session.commit()
    await session.refresh(admin)
    await session.refresh(representative)

    admin_headers = {"Authorization": f"Bearer {create_access_token(admin)}"}
    representative_token = create_access_token(representative)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        listed = await client.get("/api/v1/admin/managed-users", headers=admin_headers)
        blocked = await client.patch(
            f"/api/v1/admin/users/{representative.id}/status",
            json={"is_active": False},
            headers=admin_headers,
        )
        self_block = await client.patch(
            f"/api/v1/admin/users/{admin.id}/status",
            json={"is_active": False},
            headers=admin_headers,
        )
        blocked_me = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {representative_token}"},
        )

    assert listed.status_code == 200
    assert len(listed.json()) == 2
    assert blocked.status_code == 200 and blocked.json()["is_active"] is False
    assert self_block.status_code == 422
    assert blocked_me.status_code == 401
