from httpx import ASGITransport, AsyncClient

from app.auth import hash_password
from app.database import SessionFactory
from app.main import app
from app.models import User, UserRole


async def _create_user(login: str, password: str, role: UserRole = UserRole.ADMIN) -> str:
    async with SessionFactory() as session:
        user = User(name=f"Пользователь {login}", login=login, password_hash=hash_password(password), role=role)
        session.add(user)
        await session.commit()
        return str(user.id)


async def _login(client: AsyncClient, login: str, password: str):
    return await client.post("/api/v1/auth/login", json={"login": login, "password": password})


async def test_change_password_invalidates_previous_token():
    await _create_user("owner", "StartPass123")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        signed_in = await _login(client, "owner", "StartPass123")
        assert signed_in.status_code == 200
        old_token = signed_in.json()["access_token"]
        headers = {"Authorization": f"Bearer {old_token}"}
        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

        changed = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "StartPass123", "new_password": "NewSecure456"},
            headers=headers,
        )
        assert changed.status_code == 200
        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
        assert (await _login(client, "owner", "StartPass123")).status_code == 401
        fresh = await _login(client, "owner", "NewSecure456")
        assert fresh.status_code == 200
        assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh.json()['access_token']}"})).status_code == 200


async def test_admin_reset_invalidates_target_sessions():
    await _create_user("admin-sec", "AdminSecure123")
    target_id = await _create_user("rep-sec", "RepSecure123", UserRole.REPRESENTATIVE)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        admin_login = await _login(client, "admin-sec", "AdminSecure123")
        rep_login = await _login(client, "rep-sec", "RepSecure123")
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        rep_headers = {"Authorization": f"Bearer {rep_login.json()['access_token']}"}

        reset = await client.post(
            f"/api/v1/admin/users/{target_id}/reset-password",
            json={"new_password": "RepChanged456"},
            headers=admin_headers,
        )
        assert reset.status_code == 200
        assert (await client.get("/api/v1/auth/me", headers=rep_headers)).status_code == 401
        assert (await _login(client, "rep-sec", "RepSecure123")).status_code == 401
        assert (await _login(client, "rep-sec", "RepChanged456")).status_code == 200


async def test_new_password_policy_rejects_weak_password():
    await _create_user("secure-user", "StartSecure123")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        signed_in = await _login(client, "secure-user", "StartSecure123")
        headers = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}
        weak = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "StartSecure123", "new_password": "abcdefghij"},
            headers=headers,
        )
    assert weak.status_code == 422
    assert "буквы и цифры" in weak.json()["detail"]
