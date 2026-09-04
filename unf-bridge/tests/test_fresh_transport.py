from __future__ import annotations

from typing import Any

import pytest

from unf_bridge.fresh_transport import FreshTransport
from unf_bridge.odata import ODataEntitySet
from unf_bridge.tenant_config import TenantMapping


MAPPING_DATA = {
    "provider": "1cfresh",
    "application_url": "https://1cfresh.example/a/unf/100",
    "timezone": "Europe/Moscow",
    "post_documents": True,
    "resources": {
        "products": "Catalog_Номенклатура",
        "price_types": "Catalog_ВидыЦен",
        "prices": "InformationRegister_ЦеныНоменклатуры",
        "warehouses": "Catalog_Склады",
        "organizations": "Catalog_Организации",
        "counterparties": "Catalog_Контрагенты",
        "transfer": "Document_ПеремещениеЗапасов",
        "sale": "Document_РасходнаяНакладная",
        "cash_receipt": "Document_ПоступлениеВКассу",
        "stock_receipt": "Document_ОприходованиеЗапасов",
        "stock_writeoff": "Document_СписаниеЗапасов",
    },
    "external_key_fields": {
        "transfer": "Комментарий",
        "sale": "Комментарий",
        "cash_receipt": "Комментарий",
        "stock_receipt": "Комментарий",
        "stock_writeoff": "Комментарий",
    },
    "constants": {
        "retail_price_type_ref": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "wholesale_price_type_ref": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    },
}


class FakeClient:
    def __init__(self) -> None:
        self.existing: dict[str, Any] | None = None
        self.find_calls: list[tuple[str, str, str]] = []
        self.create_calls: list[tuple[str, dict[str, Any]]] = []
        self.post_calls: list[tuple[str, str]] = []

    def entity_sets(self) -> list[ODataEntitySet]:
        document_resources = set(MAPPING_DATA["external_key_fields"])
        by_alias = MAPPING_DATA["resources"]
        return [
            ODataEntitySet(
                name=name,
                entity_type=f"StandardODATA.{name}",
                properties=("Ref_Key", "Комментарий") if alias in document_resources else ("Ref_Key",),
            )
            for alias, name in by_alias.items()
        ]

    def find_one_by_text_field(self, resource: str, field: str, value: str) -> dict[str, Any] | None:
        self.find_calls.append((resource, field, value))
        return self.existing

    def create(self, resource: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.create_calls.append((resource, dict(payload)))
        return {"Ref_Key": "55555555-5555-5555-5555-555555555555", "Posted": False}

    def post_document(self, resource: str, ref_key: str) -> None:
        self.post_calls.append((resource, ref_key))


def test_transport_validates_mapping_against_metadata():
    client = FakeClient()
    transport = FreshTransport(client, TenantMapping.from_dict(MAPPING_DATA))  # type: ignore[arg-type]
    transport.validate_configuration()


def test_transport_reuses_existing_document_without_second_create():
    client = FakeClient()
    client.existing = {"Ref_Key": "66666666-6666-6666-6666-666666666666"}
    transport = FreshTransport(client, TenantMapping.from_dict(MAPPING_DATA))  # type: ignore[arg-type]

    result = transport.ensure_document(
        "sale",
        "ceh-sklad:stock_document:abc",
        {"СуммаДокумента": 100},
    )

    assert result.ref_key == "66666666-6666-6666-6666-666666666666"
    assert result.repeated is True
    assert client.create_calls == []
    assert client.post_calls == []


def test_transport_creates_with_external_key_and_posts_when_enabled():
    client = FakeClient()
    transport = FreshTransport(client, TenantMapping.from_dict(MAPPING_DATA))  # type: ignore[arg-type]

    result = transport.ensure_document(
        "sale",
        "ceh-sklad:stock_document:abc",
        {"СуммаДокумента": 100, "Комментарий": "пользовательский текст"},
    )

    assert result.repeated is False
    assert client.find_calls == [
        ("Document_РасходнаяНакладная", "Комментарий", "ceh-sklad:stock_document:abc")
    ]
    assert client.create_calls == [
        (
            "Document_РасходнаяНакладная",
            {"СуммаДокумента": 100, "Комментарий": "ceh-sklad:stock_document:abc"},
        )
    ]
    assert client.post_calls == [
        ("Document_РасходнаяНакладная", "55555555-5555-5555-5555-555555555555")
    ]


def test_transport_fails_if_created_document_has_no_ref_key():
    client = FakeClient()
    client.create = lambda resource, payload: {}  # type: ignore[method-assign]
    transport = FreshTransport(client, TenantMapping.from_dict(MAPPING_DATA))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="Ref_Key"):
        transport.ensure_document("sale", "ceh-sklad:key", {})


def test_transport_rejects_unknown_document_alias():
    client = FakeClient()
    transport = FreshTransport(client, TenantMapping.from_dict(MAPPING_DATA))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Неизвестный тип"):
        transport.ensure_document("unknown", "ceh-sklad:key", {})
