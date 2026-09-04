from __future__ import annotations

import json

import httpx
import pytest

from unf_bridge.odata import FreshODataClient


METADATA = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices>
    <Schema xmlns="http://schemas.microsoft.com/ado/2009/11/edm" Namespace="StandardODATA">
      <EntityType Name="Catalog_Номенклатура">
        <Property Name="Ref_Key" Type="Edm.Guid" Nullable="false" />
        <Property Name="Description" Type="Edm.String" />
      </EntityType>
      <EntityType Name="Document_РасходнаяНакладная">
        <Property Name="Ref_Key" Type="Edm.Guid" Nullable="false" />
        <Property Name="Комментарий" Type="Edm.String" />
        <Property Name="Posted" Type="Edm.Boolean" />
      </EntityType>
      <EntityContainer Name="Container">
        <EntitySet Name="Catalog_Номенклатура" EntityType="StandardODATA.Catalog_Номенклатура" />
        <EntitySet Name="Document_РасходнаяНакладная" EntityType="StandardODATA.Document_РасходнаяНакладная" />
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""


def test_fresh_odata_rejects_non_https_by_default():
    with pytest.raises(ValueError, match="HTTPS"):
        FreshODataClient("http://example.invalid/a/unf/1", "service", "secret")


def test_metadata_discovers_entity_sets_properties_and_does_not_follow_redirects():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/odata/standard.odata/$metadata")
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(200, text=METADATA, headers={"Content-Type": "application/xml"})

    with FreshODataClient(
        "https://1cfresh.example/a/unf/100",
        "service",
        "secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        entity_sets = client.entity_sets()

    assert [item.name for item in entity_sets] == [
        "Catalog_Номенклатура",
        "Document_РасходнаяНакладная",
    ]
    by_name = {item.name: item for item in entity_sets}
    assert by_name["Catalog_Номенклатура"].properties == ("Ref_Key", "Description")
    assert "Комментарий" in by_name["Document_РасходнаяНакладная"].properties
    assert "Posted" in by_name["Document_РасходнаяНакладная"].properties


def test_list_create_and_post_document_use_standard_odata_contract():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            assert request.url.path.endswith("/Catalog_Номенклатура")
            assert request.url.params["$format"] == "json"
            assert request.url.params["$top"] == "2"
            assert request.url.params["$select"] == "Ref_Key,Description"
            return httpx.Response(
                200,
                json={"value": [{"Ref_Key": "11111111-1111-1111-1111-111111111111", "Description": "Товар"}]},
            )
        if request.url.path.endswith("/Document_РасходнаяНакладная"):
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["Comment"] == "ceh-sklad:test"
            return httpx.Response(
                201,
                json={"Ref_Key": "22222222-2222-2222-2222-222222222222", "Posted": False},
            )
        assert request.url.path.endswith(
            "/Document_РасходнаяНакладная(guid'22222222-2222-2222-2222-222222222222')/Post()"
        )
        return httpx.Response(200)

    with FreshODataClient(
        "https://1cfresh.example/a/unf/100",
        "service",
        "secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        rows = client.list(
            "Catalog_Номенклатура",
            top=2,
            select=("Ref_Key", "Description"),
        )
        created = client.create("Document_РасходнаяНакладная", {"Comment": "ceh-sklad:test"})
        client.post_document("Document_РасходнаяНакладная", created["Ref_Key"])

    assert rows[0]["Description"] == "Товар"
    assert created["Posted"] is False
    assert [request.method for request in requests] == ["GET", "POST", "POST"]


def test_find_one_by_external_key_escapes_quotes_and_returns_single_match():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.params["$top"] == "2"
        assert request.url.params["$filter"] == "Комментарий eq 'ceh-sklad:O''Brien'"
        return httpx.Response(
            200,
            json={"value": [{"Ref_Key": "33333333-3333-3333-3333-333333333333"}]},
        )

    with FreshODataClient(
        "https://1cfresh.example/a/unf/100",
        "service",
        "secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        found = client.find_one_by_text_field(
            "Document_РасходнаяНакладная",
            "Комментарий",
            "ceh-sklad:O'Brien",
        )

    assert found is not None
    assert found["Ref_Key"] == "33333333-3333-3333-3333-333333333333"


def test_find_one_by_external_key_rejects_duplicates():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "value": [
                    {"Ref_Key": "33333333-3333-3333-3333-333333333333"},
                    {"Ref_Key": "44444444-4444-4444-4444-444444444444"},
                ]
            },
        )
    )
    with FreshODataClient(
        "https://1cfresh.example/a/unf/100",
        "service",
        "secret",
        transport=transport,
    ) as client:
        with pytest.raises(RuntimeError, match="Нарушена идемпотентность"):
            client.find_one_by_text_field(
                "Document_РасходнаяНакладная",
                "Комментарий",
                "ceh-sklad:stock_document:123",
            )


def test_resource_and_ref_key_are_validated_before_request():
    transport = httpx.MockTransport(lambda request: pytest.fail(f"Неожиданный запрос: {request.url}"))
    with FreshODataClient(
        "https://1cfresh.example/a/unf/100",
        "service",
        "secret",
        transport=transport,
    ) as client:
        with pytest.raises(ValueError, match="ресурса"):
            client.list("../secrets")
        with pytest.raises(ValueError, match="Ref_Key"):
            client.post_document("Document_Test", "not-a-guid")
