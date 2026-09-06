from httpx import ASGITransport, AsyncClient

from app.main import app
from app.version import APP_VERSION


async def test_liveness_readiness_and_openapi_version():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.get("/health")
        ready = await client.get("/health/ready")
        openapi = await client.get("/openapi.json")

    assert live.status_code == 200
    assert live.json() == {"status": "ok", "version": APP_VERSION}

    assert ready.status_code == 200
    ready_payload = ready.json()
    assert ready_payload["status"] == "ready"
    assert ready_payload["database"] == "ok"
    assert ready_payload["schema_revision"] == "20260904_09"
    assert ready_payload["version"] == APP_VERSION

    assert openapi.status_code == 200
    assert openapi.json()["info"]["version"] == APP_VERSION
