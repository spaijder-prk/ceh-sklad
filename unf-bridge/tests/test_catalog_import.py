from decimal import Decimal

from unf_bridge.catalog_import import FreshProductImporter, ProductFieldMapping
from unf_bridge.odata import ODataEntitySet
from unf_bridge.price_reader import ProductPrices
from unf_bridge.tenant_config import TenantMapping


PRODUCT_REF = "11111111-1111-1111-1111-111111111111"

BASE = {
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
    },
    "product_fields": {
        "ref": "Ref_Key",
        "sku": "Code",
        "name": "Description",
        "unit_name": "Единица",
    },
}


class FakeFresh:
    def list(self, resource, *, top=50, select=(), filter_expression=None):
        assert resource == "Catalog_Номенклатура"
        assert set(select) == {"Ref_Key", "Code", "Description", "Единица"}
        return [{"Ref_Key": PRODUCT_REF, "Code": "A-1", "Description": "Тестовый товар", "Единица": "шт"}]


class FakePrices:
    def __init__(self, retail="100", wholesale="80") -> None:
        self.retail = retail
        self.wholesale = wholesale

    def product_prices(self, product_ref: str) -> ProductPrices:
        assert product_ref == PRODUCT_REF
        return ProductPrices(
            retail=Decimal(self.retail) if self.retail is not None else None,
            wholesale=Decimal(self.wholesale) if self.wholesale is not None else None,
        )


class FakeCeh:
    def __init__(self) -> None:
        self.payloads = []

    def import_product(self, payload):
        self.payloads.append(dict(payload))
        return {"internal_id": "ceh-product-1", "repeated": False}


def importer(prices: FakePrices | None = None):
    mapping = TenantMapping.from_dict(BASE)
    product_mapping = ProductFieldMapping.from_dict(BASE)
    ceh = FakeCeh()
    return FreshProductImporter(
        FakeFresh(),  # type: ignore[arg-type]
        ceh,  # type: ignore[arg-type]
        mapping,
        product_mapping,
        price_reader=prices or FakePrices(),  # type: ignore[arg-type]
    ), ceh


def test_product_mapping_is_checked_against_metadata():
    fields = ProductFieldMapping.from_dict(BASE)
    fields.validate_against_metadata(
        [
            ODataEntitySet(
                name="Catalog_Номенклатура",
                entity_type="StandardODATA.Catalog_Номенклатура",
                properties=("Ref_Key", "Code", "Description", "Единица"),
            )
        ],
        "Catalog_Номенклатура",
    )


def test_dry_run_builds_versioned_idempotent_payload_without_writing():
    service, ceh = importer()
    summary = service.sync(execute=False)
    assert summary.ready == 1 and summary.imported == 0
    assert ceh.payloads == []
    plan = service.plans()[0]
    assert plan.payload is not None
    assert plan.payload["retail_price"] == "100"
    assert plan.payload["wholesale_price"] == "80"
    assert plan.payload["operation_key"].startswith("unf-product:")


def test_execute_imports_and_price_change_changes_operation_key():
    service, ceh = importer(FakePrices(retail="100", wholesale="80"))
    first_key = service.plans()[0].payload["operation_key"]  # type: ignore[index]
    summary = service.sync(execute=True)
    assert summary.imported == 1 and len(ceh.payloads) == 1

    changed, _ = importer(FakePrices(retail="110", wholesale="80"))
    second_key = changed.plans()[0].payload["operation_key"]  # type: ignore[index]
    assert first_key != second_key


def test_missing_selected_price_blocks_product_and_never_writes():
    service, ceh = importer(FakePrices(retail="100", wholesale=None))
    summary = service.sync(execute=True)
    assert summary.blocked == 1
    assert ceh.payloads == []
    assert "оптового" in summary.messages[0]
