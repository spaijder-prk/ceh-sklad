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


def test_inactive_product_import_is_redirected_to_atomic_archive_endpoint():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.content.decode("utf-8")))
        return httpx.Response(200, json={"internal_id": "product-1", "repeated": False})

    client = CehSkladClient(
        "https://sklad.example",
        "service-integration-key",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.import_product(
            {
                "external_1c_id": "11111111-1111-1111-1111-111111111111",
                "operation_key": "unf-product-archive-version-1",
                "sku": "A-1",
                "name": "Товар",
                "retail_price": "100",
                "wholesale_price": "80",
                "is_active": False,
            }
        )
    finally:
        client.close()

    assert result["repeated"] is False
    assert len(seen) == 1
    method, path, body = seen[0]
    assert method == "POST"
    assert path == "/api/v1/integration/1c/products/11111111-1111-1111-1111-111111111111/archive"
    assert '"operation_key":"unf-product-archive-version-1"' in body.replace(" ", "")
