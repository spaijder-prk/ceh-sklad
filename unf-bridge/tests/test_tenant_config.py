from __future__ import annotations

import pytest

from unf_bridge.odata import ODataEntitySet
from unf_bridge.tenant_config import TenantMapping


VALID = {
    "provider": "1cfresh",
    "application_url": "https://1cfresh.example/a/unf/100",
    "timezone": "Europe/Moscow",
    "post_documents": False,
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
        "organization_ref": "11111111-1111-1111-1111-111111111111",
        "cashbox_ref": "22222222-2222-2222-2222-222222222222",
    },
}


def test_tenant_mapping_validates_required_resources_and_metadata():
    mapping = TenantMapping.from_dict(VALID)
    entity_sets = [
        ODataEntitySet(name=name, entity_type=f"StandardODATA.{name}")
        for name in VALID["resources"].values()
    ]
    mapping.validate_against_metadata(entity_sets)
    summary = mapping.public_summary()
    assert summary["provider"] == "1cfresh"
    assert summary["post_documents"] is False
    assert "retail_price_type_ref" in summary["configured_constants"]
    assert "wholesale_price_type_ref" in summary["configured_constants"]
    assert "organization_ref" in summary["configured_constants"]


def test_tenant_mapping_rejects_missing_resource():
    payload = {**VALID, "resources": {**VALID["resources"]}}
    del payload["resources"]["prices"]
    with pytest.raises(ValueError, match="prices"):
        TenantMapping.from_dict(payload)


def test_tenant_mapping_requires_external_key_field_for_each_document():
    payload = {**VALID, "external_key_fields": {**VALID["external_key_fields"]}}
    del payload["external_key_fields"]["cash_receipt"]
    with pytest.raises(ValueError, match="cash_receipt"):
        TenantMapping.from_dict(payload)


def test_tenant_mapping_requires_two_explicit_price_types():
    payload = {**VALID, "constants": {**VALID["constants"]}}
    del payload["constants"]["wholesale_price_type_ref"]
    with pytest.raises(ValueError, match="wholesale_price_type_ref"):
        TenantMapping.from_dict(payload)

    payload = {**VALID, "constants": {**VALID["constants"]}}
    payload["constants"]["wholesale_price_type_ref"] = payload["constants"]["retail_price_type_ref"]
    with pytest.raises(ValueError, match="должны быть разными"):
        TenantMapping.from_dict(payload)


def test_tenant_mapping_rejects_invalid_ref_guid():
    payload = {**VALID, "constants": {**VALID["constants"], "cashbox_ref": "not-a-guid"}}
    with pytest.raises(ValueError, match="cashbox_ref"):
        TenantMapping.from_dict(payload)


def test_tenant_mapping_fails_before_write_if_resource_is_absent_from_metadata():
    mapping = TenantMapping.from_dict(VALID)
    entity_sets = [
        ODataEntitySet(name=name, entity_type=f"StandardODATA.{name}")
        for alias, name in VALID["resources"].items()
        if alias != "stock_writeoff"
    ]
    with pytest.raises(ValueError, match="Document_СписаниеЗапасов"):
        mapping.validate_against_metadata(entity_sets)


def test_tenant_mapping_fails_if_external_key_field_is_absent_from_metadata():
    mapping = TenantMapping.from_dict(VALID)
    entity_sets = []
    for alias, name in VALID["resources"].items():
        properties = ("Ref_Key", "Комментарий") if alias in VALID["external_key_fields"] else ("Ref_Key",)
        if alias == "sale":
            properties = ("Ref_Key", "Description")
        entity_sets.append(
            ODataEntitySet(
                name=name,
                entity_type=f"StandardODATA.{name}",
                properties=properties,
            )
        )

    with pytest.raises(ValueError, match=r"sale: Document_РасходнаяНакладная\.Комментарий"):
        mapping.validate_against_metadata(entity_sets)


def test_tenant_mapping_requires_https():
    payload = {**VALID, "application_url": "http://1cfresh.example/a/unf/100"}
    with pytest.raises(ValueError, match="HTTPS"):
        TenantMapping.from_dict(payload)
