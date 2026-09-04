from datetime import UTC, datetime
from decimal import Decimal

import pytest

from unf_bridge.models import UnfLine, UnfOutboxItem
from unf_bridge.operation_payloads import UnfOperationPayloadFactory
from unf_bridge.planner import PlannedDocument
from unf_bridge.tenant_config import TenantMapping


REPRESENTATIVE_REF = "55555555-5555-5555-5555-555555555555"
PAYER_REF = "66666666-6666-6666-6666-666666666666"

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
        "organization_ref": "11111111-1111-1111-1111-111111111111",
        "cashbox_ref": "22222222-2222-2222-2222-222222222222",
        "cash_flow_item_ref": "33333333-3333-3333-3333-333333333333",
        "retail_customer_ref": "77777777-7777-7777-7777-777777777777",
        "wholesale_customer_ref": "88888888-8888-8888-8888-888888888888",
    },
    "representative_payer_refs": {REPRESENTATIVE_REF: PAYER_REF},
    "payload_schemas": {
        "transfer": {
            "header_fields": {"date": "Дата", "organization_ref": "Организация_Key", "source_location_ref": "Откуда_Key", "destination_location_ref": "Куда_Key"},
            "table": {"property": "Запасы", "row_resource": "TransferRows", "fields": {"product_ref": "Номенклатура_Key", "quantity": "Количество"}},
        },
        "sale": {
            "header_fields": {"date": "Дата", "organization_ref": "Организация_Key", "warehouse_ref": "Склад_Key", "customer_ref": "Контрагент_Key"},
            "table": {"property": "Запасы", "row_resource": "SaleRows", "fields": {"product_ref": "Номенклатура_Key", "quantity": "Количество", "unit_price": "Цена"}},
        },
        "cash_receipt": {
            "header_fields": {"date": "Дата", "organization_ref": "Организация_Key", "cashbox_ref": "Касса_Key", "cash_flow_item_ref": "СтатьяДДС_Key", "payer_ref": "Плательщик_Key", "amount": "СуммаДокумента"}
        },
        "stock_receipt": {
            "header_fields": {"date": "Дата", "organization_ref": "Организация_Key", "warehouse_ref": "Склад_Key"},
            "table": {"property": "Запасы", "row_resource": "ReceiptRows", "fields": {"product_ref": "Номенклатура_Key", "quantity": "Количество"}},
        },
        "stock_writeoff": {
            "header_fields": {"date": "Дата", "organization_ref": "Организация_Key", "warehouse_ref": "Склад_Key"},
            "table": {"property": "Запасы", "row_resource": "WriteoffRows", "fields": {"product_ref": "Номенклатура_Key", "quantity": "Количество"}},
        },
    },
}


def line(sku: str, ref: str, quantity: str, delta: str | None = None, price: str | None = None) -> UnfLine:
    return UnfLine(
        product_external_1c_id=ref,
        sku=sku,
        quantity=Decimal(quantity),
        quantity_delta=Decimal(delta) if delta is not None else None,
        unit_price=Decimal(price) if price is not None else None,
    )


def item(**changes) -> UnfOutboxItem:
    data = dict(
        entity_type="stock_document",
        internal_id="abc",
        kind="sale",
        unf_document="Расходная накладная",
        unf_operation="Продажа",
        ready_for_unf=True,
        blocking_reasons=(),
        requires_split=False,
        source_location_external_1c_id="99999999-9999-9999-9999-999999999999",
        destination_location_external_1c_id=None,
        adjustment_location_external_1c_id=None,
        representative_external_1c_id=None,
        amount=None,
        comment=None,
        lines=(line("SKU", "44444444-4444-4444-4444-444444444444", "2", price="120"),),
        created_at=datetime(2026, 9, 4, 8, 30, tzinfo=UTC),
        sale_price_type="wholesale",
    )
    data.update(changes)
    return UnfOutboxItem(**data)


def test_sale_uses_persisted_price_type_customer_and_historical_line_price():
    factory = UnfOperationPayloadFactory(TenantMapping.from_dict(MAPPING))
    payload = factory(
        item(),
        PlannedDocument("key", "Расходная накладная", "Продажа", ("SKU",)),
    )
    assert payload["Контрагент_Key"] == MAPPING["constants"]["wholesale_customer_ref"]
    assert payload["Склад_Key"] == "99999999-9999-9999-9999-999999999999"
    assert payload["Запасы"][0]["Цена"] == 120
    assert payload["Запасы"][0]["LineNumber"] == 1


def test_cash_handover_uses_separate_representative_payer_mapping():
    factory = UnfOperationPayloadFactory(TenantMapping.from_dict(MAPPING))
    cash = item(
        entity_type="cash_handover",
        kind="cash_handover",
        unf_document="Поступление в кассу",
        unf_operation="Сдача денег",
        source_location_external_1c_id=None,
        representative_external_1c_id=REPRESENTATIVE_REF,
        amount=Decimal("1500"),
        lines=(),
        sale_price_type=None,
    )
    payload = factory(
        cash,
        PlannedDocument("cash-key", "Поступление в кассу", "Сдача денег", ()),
    )
    assert payload["Плательщик_Key"] == PAYER_REF
    assert payload["СуммаДокумента"] == 1500


def test_mixed_adjustment_documents_receive_only_their_delta_sign():
    factory = UnfOperationPayloadFactory(TenantMapping.from_dict(MAPPING))
    adjustment = item(
        kind="adjustment",
        unf_document="Оприходование запасов + Списание запасов",
        unf_operation="Корректировка",
        requires_split=True,
        source_location_external_1c_id=None,
        adjustment_location_external_1c_id="99999999-9999-9999-9999-999999999999",
        sale_price_type=None,
        lines=(
            line("PLUS", "44444444-4444-4444-4444-444444444444", "2", delta="2"),
            line("MINUS", "55555555-5555-5555-5555-555555555554", "3", delta="-3"),
        ),
    )
    receipt = factory(
        adjustment,
        PlannedDocument("r", "Оприходование запасов", "Плюс", ("PLUS",)),
    )
    writeoff = factory(
        adjustment,
        PlannedDocument("w", "Списание запасов", "Минус", ("MINUS",)),
    )
    assert [row["Количество"] for row in receipt["Запасы"]] == [2]
    assert [row["Количество"] for row in writeoff["Запасы"]] == [3]


def test_factory_fails_without_sale_type_or_payer_mapping():
    factory = UnfOperationPayloadFactory(TenantMapping.from_dict(MAPPING))
    with pytest.raises(ValueError, match="тип цены"):
        factory(
            item(sale_price_type=None),
            PlannedDocument("key", "Расходная накладная", "Продажа", ("SKU",)),
        )

    missing_payer_mapping = {**MAPPING, "representative_payer_refs": {}}
    cash_factory = UnfOperationPayloadFactory(TenantMapping.from_dict(missing_payer_mapping))
    cash = item(
        entity_type="cash_handover",
        kind="cash_handover",
        unf_document="Поступление в кассу",
        source_location_external_1c_id=None,
        representative_external_1c_id=REPRESENTATIVE_REF,
        amount=Decimal("10"),
        lines=(),
        sale_price_type=None,
    )
    with pytest.raises(ValueError, match="representative_payer_refs"):
        cash_factory(
            cash,
            PlannedDocument("cash", "Поступление в кассу", "Сдача", ()),
        )
