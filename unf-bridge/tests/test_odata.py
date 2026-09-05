import json

import httpx

from unf_bridge.odata import FreshODataClient


def test_find_one_by_guid_uses_safe_standard_ref_key_filter():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={"value": [{"Ref_Key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}]},
        )

    client = FreshODataClient(
        "https://fresh.example/a/demo",
        "service",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        row = client.find_one_by_guid(
            "Catalog_Организации",
            "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
        )
    finally:
        client.close()

    assert row == {"Ref_Key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
    assert seen["path"].endswith("/Catalog_Организации")
    assert seen["query"]["$select"] == "Ref_Key"
    assert seen["query"]["$top"] == "2"
    assert seen["query"]["$filter"] == "Ref_Key eq guid'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'"


def test_find_one_by_guid_rejects_invalid_guid_without_request():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = FreshODataClient(
        "https://fresh.example/a/demo",
        "service",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        try:
            client.find_one_by_guid("Catalog_Организации", "not-guid")
        except ValueError as exc:
            assert "Ref_Key" in str(exc)
        else:
            raise AssertionError("Ожидался ValueError")
    finally:
        client.close()
    assert called is False
