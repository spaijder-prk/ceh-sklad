from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from unf_bridge.odata import ODataEntitySet, ODataField, ODataNavigation
from unf_bridge.payload_builder import MappedDocumentPayloadBuilder
from unf_bridge.tenant_config import TenantMapping


MAPPING = {
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
    "price_fields": {
        "product_ref": "Номенклатура_Key",
        "price_type_ref": "ВидЦен_Key",
        "value": "Цена",
    },
    "constants": {
        "retail_price_type_ref": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "wholesale_price_type_ref": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    },
    "payload_schemas": {
        "sale": {
            "header_fields": {
                "date": "Дата",
                "organization_ref": "Организация_Key",
                "warehouse_ref": "Склад_Key",
                "customer_ref": "Контрагент_Key",
            },
            "table": {
                "property": "Запасы",
                "row_resource": "Document_РасходнаяНакладная_Запасы_RecordType",
                "fields": {
                    "product_ref": "Номенклатура_Key",
                    "quantity": "Количество",
                    "unit_price": "Цена",
                },
            },
        },
        "cash_receipt": {
            "header_fields": {
                "date": "Дата",
                "organization_ref": "Организация_Key",
                "cashbox_ref": "Касса_Key",
                "amount": "СуммаДокумента",
            }
        },
    },
}


def test_builder_maps_header_table_rows_and_json_scalars():
    builder = MappedDocumentPayloadBuilder(TenantMapping.from_dict(MAPPING))
    payload = builder.build(
        "sale",
        {
            "date": date(2026, 9, 4),
            "organization_ref": "11111111-1111-1111-1111-111111111111",
            "warehouse_ref": "22222222-2222-2222-2222-222222222222",
            "customer_ref": None,
        },
        [
            {
                "product_ref": "33333333-3333-3333-3333-333333333333",
                "quantity": Decimal("2"),
                "unit_price": Decimal("125.50"),
            },
            {
                "product_ref": "44444444-4444-4444-4444-444444444444",
                "quantity": Decimal("0.75"),
                "unit_price": Decimal("80"),
            },
        ],
    )
    assert payload == {
        "Дата": "2026-09-04",
        "Организация_Key": "11111111-1111-1111-1111-111111111111",
        "Склад_Key": "22222222-2222-2222-2222-222222222222",
        "Запасы": [
            {
                "Номенклатура_Key": "33333333-3333-3333-3333-333333333333",
                "Количество": 2,
                "Цена": 125.5,
                "LineNumber": 1,
            },
            {
                "Номенклатура_Key": "44444444-4444-4444-4444-444444444444",
                "Количество": 0.75,
                "Цена": 80,
                "LineNumber": 2,
            },
        ],
    }


def test_builder_supports_header_only_document_and_rejects_unknown_semantics():
    builder = MappedDocumentPayloadBuilder(TenantMapping.from_dict(MAPPING))
    payload = builder.build(
        "cash_receipt",
        {
            "date": date(2026, 9, 4),
            "organization_ref": "11111111-1111-1111-1111-111111111111",
            "cashbox_ref": "55555555-5555-5555-5555-555555555555",
            "amount": Decimal("1000.00"),
        },
    )
    assert payload["СуммаДокумента"] == 1000
    with pytest.raises(ValueError, match="не настроены semantic aliases"):
        builder.build("cash_receipt", {"unknown": 1})
    with pytest.raises(ValueError, match="не задан payload_schemas"):
        builder.build("transfer", {})


def test_payload_schema_is_checked_against_document_and_row_metadata():
    mapping = TenantMapping.from_dict(MAPPING)
    entities = [
        ODataEntitySet(
            name=value,
            entity_type=f"StandardODATA.{value}",
            properties=("Ref_Key", "Комментарий")
            if alias in MAPPING["external_key_fields"]
            else ("Ref_Key", "Description"),
        )
        for alias, value in MAPPING["resources"].items()
        if alias not in {"sale", "cash_receipt", "prices"}
    ]
    entities.extend(
        [
            ODataEntitySet(
                name=MAPPING["resources"]["prices"],
                entity_type="StandardODATA.InformationRegister_ЦеныНоменклатуры",
                properties=("Номенклатура_Key", "ВидЦен_Key", "Цена"),
            ),
            ODataEntitySet(
                name=MAPPING["resources"]["sale"],
                entity_type="StandardODATA.Document_РасходнаяНакладная",
                properties=("Ref_Key", "Комментарий", "Дата", "Организация_Key", "Склад_Key", "Контрагент_Key"),
                fields=(
                    ODataField("Ref_Key", "Edm.Guid", False),
                    ODataField("Комментарий", "Edm.String"),
                    ODataField("Дата", "Edm.Date"),
                    ODataField("Организация_Key", "Edm.Guid"),
                    ODataField("Склад_Key", "Edm.Guid"),
                    ODataField("Контрагент_Key", "Edm.Guid"),
                ),
                navigation=(
                    ODataNavigation(
                        "Запасы",
                        "Collection(StandardODATA.Document_РасходнаяНакладная_Запасы_RowType)",
                    ),
                ),
            ),
            ODataEntitySet(
                name="Document_РасходнаяНакладная_Запасы_RecordType",
                entity_type="StandardODATA.Document_РасходнаяНакладная_Запасы_RecordType",
                properties=("Ref_Key", "LineNumber", "Номенклатура_Key", "Количество", "Цена"),
            ),
            ODataEntitySet(
                name=MAPPING["resources"]["cash_receipt"],
                entity_type="StandardODATA.Document_ПоступлениеВКассу",
                properties=("Ref_Key", "Комментарий", "Дата", "Организация_Key", "Касса_Key", "СуммаДокумента"),
            ),
        ]
    )
    mapping.validate_against_metadata(entities)

    broken = [
        ODataEntitySet(
            name=item.name,
            entity_type=item.entity_type,
            properties=tuple(name for name in item.properties if name != "Цена"),
            fields=item.fields,
            navigation=item.navigation,
        )
        if item.name == "Document_РасходнаяНакладная_Запасы_RecordType"
        else item
        for item in entities
    ]
    with pytest.raises(ValueError, match=r"payload sale\.row\.unit_price"):
        mapping.validate_against_metadata(broken)


def test_payload_schema_rejects_line_number_override():
    payload = {**MAPPING, "payload_schemas": {**MAPPING["payload_schemas"]}}
    sale = {
        **payload["payload_schemas"]["sale"],
        "table": {
            **payload["payload_schemas"]["sale"]["table"],
            "fields": {
                **payload["payload_schemas"]["sale"]["table"]["fields"],
                "line": "LineNumber",
            },
        },
    }
    payload["payload_schemas"]["sale"] = sale
    with pytest.raises(ValueError, match="LineNumber управляется bridge"):
        TenantMapping.from_dict(payload)
