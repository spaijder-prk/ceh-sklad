import httpx

from unf_bridge.ceh_client import CehSkladClient


def test_readiness_uses_root_health_endpoint_and_service_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers.get("X-1C-Key")
        return httpx.Response(
            200,
            json={
                "status": "ready",
                "database": "ok",
                "schema_revision": "20260904_09",
            },
        )

    client = CehSkladClient(
        "https://sklad.example",
        "service-integration-key",
        transport=httpx.MockTransport(handler),
    )
    try:
        body = client.readiness()
    finally:
        client.close()

    assert seen == {"path": "/health/ready", "key": "service-integration-key"}
    assert body["status"] == "ready"
    assert body["database"] == "ok"
    assert body["schema_revision"] == "20260904_09"


def test_readiness_rejects_non_object_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["unexpected"])

    client = CehSkladClient(
        "https://sklad.example",
        "service-integration-key",
        transport=httpx.MockTransport(handler),
    )
    try:
        try:
            client.readiness()
        except RuntimeError as exc:
            assert "readiness" in str(exc)
        else:
            raise AssertionError("Ожидался RuntimeError")
    finally:
        client.close()
