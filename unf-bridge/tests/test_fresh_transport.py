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
        "products": "Catalog_Номенклатура", "price_types": "Catalog_ВидыЦен",
        "prices": "InformationRegister_ЦеныНоменклатуры", "warehouses": "Catalog_Склады",
        "organizations": "Catalog_Организации", "counterparties": "Catalog_Контрагенты",
        "transfer": "Document_ПеремещениеЗапасов", "sale": "Document_РасходнаяНакладная",
        "cash_receipt": "Document_ПоступлениеВКассу", "stock_receipt": "Document_ОприходованиеЗапасов",
        "stock_writeoff": "Document_СписаниеЗапасов",
    },
    "external_key_fields": {
        "transfer": "Комментарий", "sale": "Комментарий", "cash_receipt": "Комментарий",
        "stock_receipt": "Комментарий", "stock_writeoff": "Комментарий",
    },
    "price_fields": {"product_ref": "Номенклатура_Key", "price_type_ref": "ВидЦен_Key", "value": "Цена"},
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
        result = []
        for alias, name in MAPPING_DATA["resources"].items():
            if alias in MAPPING_DATA["external_key_fields"]:
                props = ("Ref_Key", "Комментарий")
            elif alias == "prices":
                props = ("Номенклатура_Key", "ВидЦен_Key", "Цена")
            else:
                props = ("Ref_Key",)
            result.append(ODataEntitySet(name, f"StandardODATA.{name}", props))
        return result

    def find_one_by_text_field(self, resource: str, field: str, value: str):
        self.find_calls.append((resource, field, value)); return self.existing
    def create(self, resource: str, payload: dict[str, Any]):
        self.create_calls.append((resource, dict(payload))); return {"Ref_Key": "55555555-5555-5555-5555-555555555555"}
    def post_document(self, resource: str, ref_key: str) -> None:
        self.post_calls.append((resource, ref_key))


def test_transport_validates_mapping_against_metadata():
    FreshTransport(FakeClient(), TenantMapping.from_dict(MAPPING_DATA)).validate_configuration()  # type: ignore[arg-type]


def test_transport_reuses_existing_document_without_second_create():
    client = FakeClient(); client.existing = {"Ref_Key": "66666666-6666-6666-6666-666666666666"}
    transport = FreshTransport(client, TenantMapping.from_dict(MAPPING_DATA))  # type: ignore[arg-type]
    result = transport.ensure_document("sale", "ceh-sklad:key", {"СуммаДокумента": 100})
    assert result.repeated is True and client.create_calls == [] and client.post_calls == []


def test_transport_creates_with_external_key_and_posts_when_enabled():
    client = FakeClient(); transport = FreshTransport(client, TenantMapping.from_dict(MAPPING_DATA))  # type: ignore[arg-type]
    result = transport.ensure_document("sale", "ceh-sklad:key", {"Комментарий": "old"})
    assert result.repeated is False
    assert client.create_calls[0][1]["Комментарий"] == "ceh-sklad:key"
    assert len(client.post_calls) == 1


def test_transport_rejects_unknown_alias_or_missing_ref():
    client = FakeClient(); transport = FreshTransport(client, TenantMapping.from_dict(MAPPING_DATA))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Неизвестный тип"):
        transport.ensure_document("unknown", "key", {})
    client.create = lambda resource, payload: {}  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="Ref_Key"):
        transport.ensure_document("sale", "key", {})
