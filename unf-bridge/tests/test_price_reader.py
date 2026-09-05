from __future__ import annotations

from decimal import Decimal

import pytest

from unf_bridge.price_reader import FreshPriceReader
from unf_bridge.tenant_config import TenantMapping


MAPPING = TenantMapping.from_dict({
    "provider": "1cfresh",
    "application_url": "https://1cfresh.example/a/unf/100",
    "timezone": "Europe/Moscow",
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
})


class FakeClient:
    def __init__(self, values: dict[str, list[dict]]) -> None:
        self.values = values
        self.calls: list[tuple[str, dict[str, str], tuple[str, ...]]] = []

    def slice_last_by_guid_fields(self, resource, filters, *, select=()):
        self.calls.append((resource, dict(filters), tuple(select)))
        price_type = filters["ВидЦен_Key"]
        return self.values.get(price_type, [])


def test_price_reader_reads_two_explicit_price_types():
    client = FakeClient({
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": [{"Цена": "350.00"}],
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": [{"Цена": 310}],
    })
    reader = FreshPriceReader(client, MAPPING)  # type: ignore[arg-type]

    prices = reader.product_prices("cccccccc-cccc-cccc-cccc-cccccccccccc")

    assert prices.retail == Decimal("350.00")
    assert prices.wholesale == Decimal("310")
    assert len(client.calls) == 2
    assert client.calls[0][0] == "InformationRegister_ЦеныНоменклатуры"
    assert client.calls[0][1]["Номенклатура_Key"] == "cccccccc-cccc-cccc-cccc-cccccccccccc"


def test_price_reader_returns_none_when_price_is_not_set():
    reader = FreshPriceReader(FakeClient({}), MAPPING)  # type: ignore[arg-type]
    prices = reader.product_prices("cccccccc-cccc-cccc-cccc-cccccccccccc")
    assert prices.retail is None
    assert prices.wholesale is None


def test_price_reader_rejects_ambiguous_or_negative_price():
    retail = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    reader = FreshPriceReader(FakeClient({retail: [{"Цена": 1}, {"Цена": 2}]}), MAPPING)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="несколько цен"):
        reader.product_prices("cccccccc-cccc-cccc-cccc-cccccccccccc")

    reader = FreshPriceReader(FakeClient({retail: [{"Цена": -1}]}), MAPPING)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="отрицательную цену"):
        reader.product_prices("cccccccc-cccc-cccc-cccc-cccccccccccc")
