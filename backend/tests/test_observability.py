from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability import install_observability


def create_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/items/{item_id}")
    def item(item_id: str):
        return {"item_id": item_id}

    install_observability(app)
    return app


def test_request_id_is_echoed_and_route_is_exported_to_metrics():
    client = TestClient(create_test_app())

    response = client.get("/items/42", headers={"X-Request-ID": "test-request-42"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-42"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "ceh_http_requests_total" in metrics.text
    assert 'route="/items/{item_id}"' in metrics.text


def test_invalid_request_id_is_replaced():
    client = TestClient(create_test_app())

    response = client.get("/items/1", headers={"X-Request-ID": "bad request id with spaces"})

    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]
    assert request_id != "bad request id with spaces"
    assert len(request_id) == 32
    assert request_id.isalnum()


def test_unmatched_path_uses_bounded_metric_label():
    client = TestClient(create_test_app())

    response = client.get("/secret-or-random-path-123")

    assert response.status_code == 404
    metrics = client.get("/metrics")
    assert 'route="__unmatched__"' in metrics.text
    assert 'route="/secret-or-random-path-123"' not in metrics.text
