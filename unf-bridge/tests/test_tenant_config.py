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
        "transfer": "Комментарий", "sale": "Комментарий", "cash_receipt": "Комментарий",
        "stock_receipt": "Комментарий", "stock_writeoff": "Комментарий",
    },
    "price_fields": {
        "product_ref": "Номенклатура_Key",
        "price_type_ref": "ВидЦен_Key",
        "value": "Цена",
    },
    "constants": {
        "retail_price_type_ref": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "wholesale_price_type_ref": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "organization_ref": "11111111-1111-1111-1111-111111111111",
    },
}


def metadata_sets():
    result = []
    for alias, name in VALID["resources"].items():
        if alias in VALID["external_key_fields"]:
            props = ("Ref_Key", "Комментарий")
        elif alias == "prices":
            props = ("Номенклатура_Key", "ВидЦен_Key", "Цена", "Period")
        else:
            props = ("Ref_Key", "Description")
        result.append(ODataEntitySet(name=name, entity_type=f"StandardODATA.{name}", properties=props))
    return result


def test_tenant_mapping_validates_resources_document_fields_and_price_fields():
    mapping = TenantMapping.from_dict(VALID)
    mapping.validate_against_metadata(metadata_sets())
    assert mapping.price_fields["value"] == "Цена"
    assert "retail_price_type_ref" in mapping.public_summary()["configured_constants"]


def test_tenant_mapping_requires_price_fields():
    payload = {**VALID, "price_fields": {**VALID["price_fields"]}}
    del payload["price_fields"]["value"]
    with pytest.raises(ValueError, match="value"):
        TenantMapping.from_dict(payload)


def test_tenant_mapping_requires_two_distinct_price_types():
    payload = {**VALID, "constants": {**VALID["constants"]}}
    del payload["constants"]["wholesale_price_type_ref"]
    with pytest.raises(ValueError, match="wholesale_price_type_ref"):
        TenantMapping.from_dict(payload)
    payload = {**VALID, "constants": {**VALID["constants"]}}
    payload["constants"]["wholesale_price_type_ref"] = payload["constants"]["retail_price_type_ref"]
    with pytest.raises(ValueError, match="должны быть разными"):
        TenantMapping.from_dict(payload)


def test_tenant_mapping_detects_wrong_price_field_in_metadata():
    mapping = TenantMapping.from_dict(VALID)
    sets = metadata_sets()
    price_name = VALID["resources"]["prices"]
    sets = [
        ODataEntitySet(item.name, item.entity_type, ("Номенклатура_Key", "ВидЦен_Key", "Стоимость"))
        if item.name == price_name else item
        for item in sets
    ]
    with pytest.raises(ValueError, match=r"prices: .*\.Цена"):
        mapping.validate_against_metadata(sets)


def test_tenant_mapping_detects_missing_resource_and_wrong_guid():
    mapping = TenantMapping.from_dict(VALID)
    with pytest.raises(ValueError, match="Списание"):
        mapping.validate_against_metadata([x for x in metadata_sets() if x.name != VALID["resources"]["stock_writeoff"]])
    payload = {**VALID, "constants": {**VALID["constants"], "organization_ref": "not-a-guid"}}
    with pytest.raises(ValueError, match="organization_ref"):
        TenantMapping.from_dict(payload)


def test_tenant_mapping_requires_https():
    payload = {**VALID, "application_url": "http://1cfresh.example/a/unf/100"}
    with pytest.raises(ValueError, match="HTTPS"):
        TenantMapping.from_dict(payload)
