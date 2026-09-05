from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_preflight import run_preflight, validate_base_url  # noqa: E402


SCHEMA = "20260904_09"


def test_release_preflight_ready_and_uses_service_key_only_for_integration():
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers.get("X-1C-Key")))
        if request.url.path == "/health/ready":
            return httpx.Response(
                200,
                json={"status": "ready", "database": "ok", "schema_revision": SCHEMA},
            )
        if request.url.path == "/api/v1/integration/1c/unf/profile":
            return httpx.Response(
                200,
                json={
                    "contract_version": "unf-cloud-v2",
                    "target_configuration": "1С:Управление нашей фирмой",
                    "deployment": "cloud",
                },
            )
        if request.url.path == "/api/v1/integration/1c/unf/outbox":
            assert request.url.params.get("limit") == "100"
            return httpx.Response(200, json=[{"internal_id": "doc-1", "kind": "sale", "ready_for_unf": True}])
        raise AssertionError(request.url)

    report = run_preflight(
        "https://staging.example.test",
        integration_key="service-key",
        expected_schema_revision=SCHEMA,
        require_unf_ready=True,
        transport=httpx.MockTransport(handler),
    )

    assert report.status == "ready"
    assert report.schema_revision == SCHEMA
    assert report.integration_checked is True
    assert report.outbox_items == 1
    assert report.outbox_ready == 1
    assert report.outbox_blocked == 0
    assert seen[0] == ("/health/ready", None)
    assert seen[1][1] == "service-key"
    assert seen[2][1] == "service-key"
    assert "service-key" not in str(report)


def test_release_preflight_degraded_on_schema_mismatch():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health/ready"
        return httpx.Response(
            200,
            json={"status": "ready", "database": "ok", "schema_revision": "old-revision"},
        )

    report = run_preflight(
        "https://staging.example.test",
        expected_schema_revision=SCHEMA,
        transport=httpx.MockTransport(handler),
    )

    assert report.status == "degraded"
    assert any("ожидалась" in error for error in report.errors)


def test_release_preflight_strict_unf_requires_service_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health/ready"
        return httpx.Response(
            200,
            json={"status": "ready", "database": "ok", "schema_revision": SCHEMA},
        )

    report = run_preflight(
        "https://staging.example.test",
        require_unf_ready=True,
        transport=httpx.MockTransport(handler),
    )

    assert report.status == "degraded"
    assert report.integration_checked is False
    assert any("CEH_STAGING_1C_KEY" in error for error in report.errors)


def test_release_preflight_strict_unf_blocks_unmapped_outbox():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health/ready":
            return httpx.Response(
                200,
                json={"status": "ready", "database": "ok", "schema_revision": SCHEMA},
            )
        if request.url.path == "/api/v1/integration/1c/unf/profile":
            return httpx.Response(
                200,
                json={
                    "contract_version": "unf-cloud-v2",
                    "target_configuration": "1С:Управление нашей фирмой",
                    "deployment": "cloud",
                },
            )
        if request.url.path == "/api/v1/integration/1c/unf/outbox":
            return httpx.Response(
                200,
                json=[
                    {
                        "internal_id": "doc-2",
                        "kind": "transfer",
                        "ready_for_unf": False,
                        "blocking_reasons": ["Не сопоставлен склад"],
                    }
                ],
            )
        raise AssertionError(request.url)

    report = run_preflight(
        "https://staging.example.test",
        integration_key="service-key",
        require_unf_ready=True,
        transport=httpx.MockTransport(handler),
    )

    assert report.status == "degraded"
    assert report.outbox_blocked == 1
    assert report.blocking_samples == ("transfer doc-2: Не сопоставлен склад",)


@pytest.mark.parametrize(
    "url",
    [
        "http://staging.example.test",
        "https://user:password@staging.example.test",
        "https://staging.example.test/api",
        "https://staging.example.test?x=1",
    ],
)
def test_release_preflight_rejects_unsafe_base_url(url: str):
    with pytest.raises(ValueError):
        validate_base_url(url)
