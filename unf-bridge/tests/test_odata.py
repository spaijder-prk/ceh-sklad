from __future__ import annotations

import json

import httpx
import pytest

from unf_bridge.fresh_probe import entity_details_lines, related_entity_sets
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
        <Property Name="Posted" Type="Edm.Boolean" Nullable="false" />
        <NavigationProperty Name="Запасы" Type="Collection(StandardODATA.Document_РасходнаяНакладная_Запасы_RowType)" />
      </EntityType>
      <EntityType Name="Document_РасходнаяНакладная_Запасы_RecordType">
        <Property Name="LineNumber" Type="Edm.Int32" Nullable="false" />
        <Property Name="Номенклатура_Key" Type="Edm.Guid" Nullable="false" />
        <Property Name="Количество" Type="Edm.Decimal" Nullable="false" />
      </EntityType>
      <EntityContainer Name="Container">
        <EntitySet Name="Catalog_Номенклатура" EntityType="StandardODATA.Catalog_Номенклатура" />
        <EntitySet Name="Document_РасходнаяНакладная" EntityType="StandardODATA.Document_РасходнаяНакладная" />
        <EntitySet Name="Document_РасходнаяНакладная_Запасы_RecordType" EntityType="StandardODATA.Document_РасходнаяНакладная_Запасы_RecordType" />
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""


def client_with_metadata():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/odata/standard.odata/$metadata")
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(200, text=METADATA, headers={"Content-Type": "application/xml"})
    return FreshODataClient(
        "https://1cfresh.example/a/unf/100",
        "service",
        "secret",
        transport=httpx.MockTransport(handler),
    )


def test_fresh_odata_rejects_non_https_by_default():
    with pytest.raises(ValueError, match="HTTPS"):
        FreshODataClient("http://example.invalid/a/unf/1", "service", "secret")


def test_metadata_discovers_fields_types_navigation_and_tabular_entity_set():
    with client_with_metadata() as client:
        entity_sets = client.entity_sets()

    by_name = {item.name: item for item in entity_sets}
    product = by_name["Catalog_Номенклатура"]
    sale = by_name["Document_РасходнаяНакладная"]
    table = by_name["Document_РасходнаяНакладная_Запасы_RecordType"]

    assert product.properties == ("Ref_Key", "Description")
    assert product.fields[0].edm_type == "Edm.Guid"
    assert product.fields[0].nullable is False
    assert sale.navigation[0].name == "Запасы"
    assert "Collection(" in sale.navigation[0].target_type
    assert table.fields[1].name == "Номенклатура_Key"
    assert table.fields[1].edm_type == "Edm.Guid"

    related = related_entity_sets(sale, entity_sets)
    assert [item.name for item in related] == ["Document_РасходнаяНакладная_Запасы_RecordType"]
    details = "\n".join(entity_details_lines(sale, entity_sets))
    assert "Комментарий: Edm.String" in details
    assert "Запасы" in details
    assert "Номенклатура_Key: Edm.Guid" in details


def test_slice_last_builds_safe_guid_condition():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/InformationRegister_ЦеныНоменклатуры/SliceLast")
        assert request.url.params["Condition"] == (
            "Номенклатура_Key eq guid'cccccccc-cccc-cccc-cccc-cccccccccccc' and "
            "ВидЦен_Key eq guid'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'"
        )
        assert request.url.params["$select"] == "Цена"
        return httpx.Response(200, json={"value": [{"Цена": 350}]})

    with FreshODataClient(
        "https://1cfresh.example/a/unf/100",
        "service",
        "secret",
        transport=httpx.MockTransport(handler),
    ) as client:
        rows = client.slice_last_by_guid_fields(
            "InformationRegister_ЦеныНоменклатуры",
            {
                "Номенклатура_Key": "CCCCCCCC-CCCC-CCCC-CCCC-CCCCCCCCCCCC",
                "ВидЦен_Key": "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
            },
            select=("Цена",),
        )
    assert rows == [{"Цена": 350}]


def test_list_create_and_post_document_use_standard_odata_contract():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            assert request.url.path.endswith("/Catalog_Номенклатура")
            return httpx.Response(200, json={"value": [{"Description": "Товар"}]})
        if request.url.path.endswith("/Document_РасходнаяНакладная"):
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["Comment"] == "ceh-sklad:test"
            return httpx.Response(201, json={"Ref_Key": "22222222-2222-2222-2222-222222222222", "Posted": False})
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
        rows = client.list("Catalog_Номенклатура", top=2)
        created = client.create("Document_РасходнаяНакладная", {"Comment": "ceh-sklad:test"})
        client.post_document("Document_РасходнаяНакладная", created["Ref_Key"])
    assert rows[0]["Description"] == "Товар"
    assert [request.method for request in requests] == ["GET", "POST", "POST"]


def test_find_one_by_external_key_escapes_quotes_and_returns_single_match():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["$filter"] == "Комментарий eq 'ceh-sklad:O''Brien'"
        return httpx.Response(200, json={"value": [{"Ref_Key": "33333333-3333-3333-3333-333333333333"}]})

    with FreshODataClient(
        "https://1cfresh.example/a/unf/100", "service", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        found = client.find_one_by_text_field("Document_РасходнаяНакладная", "Комментарий", "ceh-sklad:O'Brien")
    assert found is not None


def test_find_one_by_external_key_rejects_duplicates():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"value": [{"Ref_Key": "1"}, {"Ref_Key": "2"}]}))
    with FreshODataClient("https://1cfresh.example/a/unf/100", "service", "secret", transport=transport) as client:
        with pytest.raises(RuntimeError, match="Нарушена идемпотентность"):
            client.find_one_by_text_field("Document_РасходнаяНакладная", "Комментарий", "ceh-sklad:key")


def test_resource_and_ref_key_are_validated_before_request():
    transport = httpx.MockTransport(lambda request: pytest.fail(f"Неожиданный запрос: {request.url}"))
    with FreshODataClient("https://1cfresh.example/a/unf/100", "service", "secret", transport=transport) as client:
        with pytest.raises(ValueError, match="ресурса"):
            client.list("../secrets")
        with pytest.raises(ValueError, match="Ref_Key"):
            client.post_document("Document_Test", "not-a-guid")
