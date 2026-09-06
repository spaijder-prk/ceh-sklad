from httpx import ASGITransport, AsyncClient

from app.auth import hash_password
from app.database import SessionFactory
from app.main import app
from app.models import User, UserRole
from app.web_security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE


async def _create_admin(login: str = "web-admin", password: str = "WebSecure123") -> None:
    async with SessionFactory() as session:
        session.add(
            User(
                name="Web Admin",
                login=login,
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
            )
        )
        await session.commit()


async def test_web_login_uses_http_only_cookie_and_csrf_not_json_token():
    await _create_admin()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/web-login",
            json={"login": "web-admin", "password": "WebSecure123"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert response.status_code == 200
        assert "access_token" not in response.json()
        assert client.cookies.get(SESSION_COOKIE)
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf
        set_cookie = "\n".join(response.headers.get_list("set-cookie")).lower()
        assert f"{SESSION_COOKIE}=" in set_cookie
        assert "httponly" in set_cookie
        assert "samesite=strict" in set_cookie

        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["login"] == "web-admin"

        blocked = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "WebSecure123", "new_password": "WebChanged456"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert blocked.status_code == 403
        assert "CSRF" in blocked.json()["detail"]

        changed = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "WebSecure123", "new_password": "WebChanged456"},
            headers={"Origin": "http://localhost:5173", CSRF_HEADER: csrf},
        )
        assert changed.status_code == 200
        assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_bearer_api_remains_usable_even_when_cookie_session_exists():
    await _create_admin("dual-admin", "DualSecure123")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        web = await client.post(
            "/api/v1/auth/web-login",
            json={"login": "dual-admin", "password": "DualSecure123"},
        )
        assert web.status_code == 200

        bearer = await client.post(
            "/api/v1/auth/login",
            json={"login": "dual-admin", "password": "DualSecure123"},
        )
        token = bearer.json()["access_token"]
        changed = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "DualSecure123", "new_password": "DualChanged456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert changed.status_code == 200


async def test_web_logout_requires_csrf_and_clears_both_cookies():
    await _create_admin("logout-admin", "LogoutSecure123")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        logged_in = await client.post(
            "/api/v1/auth/web-login",
            json={"login": "logout-admin", "password": "LogoutSecure123"},
        )
        assert logged_in.status_code == 200
        csrf = client.cookies.get(CSRF_COOKIE)
        assert csrf

        assert (await client.post("/api/v1/auth/web-logout")).status_code == 403
        logout = await client.post("/api/v1/auth/web-logout", headers={CSRF_HEADER: csrf})
        assert logout.status_code == 200
        assert client.cookies.get(SESSION_COOKIE) is None
        assert client.cookies.get(CSRF_COOKIE) is None
        assert (await client.get("/api/v1/auth/me")).status_code == 401
