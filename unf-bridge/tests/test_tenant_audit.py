from copy import deepcopy

from unf_bridge.tenant_audit import audit_mapping_data


WAREHOUSE = "11111111-1111-1111-1111-111111111111"
REPRESENTATIVE = "22222222-2222-2222-2222-222222222222"
PAYER = "33333333-3333-3333-3333-333333333333"


def _table(*fields: str) -> dict:
    return {
        "property": "Товары",
        "row_resource": "DocumentRow_Товары",
        "fields": {field: f"Поле_{field}" for field in fields},
    }


def complete_mapping() -> dict:
    return {
        "provider": "1cfresh",
        "application_url": "https://1cfresh.example/a/unf/100",
        "timezone": "Europe/Moscow",
        "post_documents": False,
        "resources": {
            "products": "Catalog_Номенклатура",
            "price_types": "Catalog_ВидыЦен",
            "prices": "InformationRegister_Цены",
            "warehouses": "Catalog_Склады",
            "organizations": "Catalog_Организации",
            "counterparties": "Catalog_Контрагенты",
            "transfer": "Document_Перемещение",
            "sale": "Document_Продажа",
            "cash_receipt": "Document_Касса",
            "stock_receipt": "Document_Оприходование",
            "stock_writeoff": "Document_Списание",
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
            "organization_ref": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "retail_customer_ref": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            "wholesale_customer_ref": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
            "cashbox_ref": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "cash_flow_item_ref": "12121212-1212-1212-1212-121212121212",
        },
        "representative_payer_refs": {REPRESENTATIVE: PAYER},
        "product_fields": {
            "ref": "Ref_Key",
            "sku": "Артикул",
            "name": "Description",
            "unit_name": "Единица",
        },
        "location_fields": {"ref": "Ref_Key", "name": "Description"},
        "location_allowlist": {
            WAREHOUSE: {"kind": "warehouse", "name_override": "Основной склад"},
            REPRESENTATIVE: {"kind": "representative", "name_override": "Представитель 1"},
        },
        "payload_schemas": {
            "transfer": {
                "header_fields": {
                    "date": "Date",
                    "organization_ref": "Организация_Key",
                    "source_location_ref": "СкладОтправитель_Key",
                    "destination_location_ref": "СкладПолучатель_Key",
                },
                "table": _table("product_ref", "quantity"),
            },
            "sale": {
                "header_fields": {
                    "date": "Date",
                    "organization_ref": "Организация_Key",
                    "warehouse_ref": "Склад_Key",
                    "customer_ref": "Покупатель_Key",
                },
                "table": _table("product_ref", "quantity", "unit_price"),
            },
            "cash_receipt": {
                "header_fields": {
                    "date": "Date",
                    "organization_ref": "Организация_Key",
                    "cashbox_ref": "Касса_Key",
                    "cash_flow_item_ref": "СтатьяДДС_Key",
                    "payer_ref": "Плательщик_Key",
                    "amount": "Сумма",
                }
            },
            "stock_receipt": {
                "header_fields": {
                    "date": "Date",
                    "organization_ref": "Организация_Key",
                    "warehouse_ref": "Склад_Key",
                },
                "table": _table("product_ref", "quantity"),
            },
            "stock_writeoff": {
                "header_fields": {
                    "date": "Date",
                    "organization_ref": "Организация_Key",
                    "warehouse_ref": "Склад_Key",
                },
                "table": _table("product_ref", "quantity"),
            },
        },
    }


def test_complete_mapping_is_ready_with_posting_warning():
    report = audit_mapping_data(complete_mapping())
    assert report.status == "ready"
    assert report.errors == ()
    assert report.payload_schema_count == 5
    assert report.location_allowlist_count == 2
    assert report.representative_count == 1
    assert report.payer_mapping_count == 1
    assert any("post_documents=false" in warning for warning in report.warnings)


def test_missing_customer_and_representative_payer_block_uat():
    data = complete_mapping()
    data["constants"]["wholesale_customer_ref"] = ""
    data["representative_payer_refs"] = {}
    report = audit_mapping_data(data)
    assert report.status == "blocked"
    assert any("wholesale_customer_ref" in error for error in report.errors)
    assert any("representative_payer_refs" in error for error in report.errors)


def test_missing_sale_row_alias_is_reported_before_network_uat():
    data = deepcopy(complete_mapping())
    del data["payload_schemas"]["sale"]["table"]["fields"]["unit_price"]
    report = audit_mapping_data(data)
    assert report.status == "blocked"
    assert any("payload_schemas.sale" in error and "unit_price" in error for error in report.errors)
