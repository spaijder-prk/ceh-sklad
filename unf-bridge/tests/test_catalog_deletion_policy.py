from decimal import Decimal

import pytest

from unf_bridge.catalog_import import FreshProductImporter, ProductFieldMapping
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
}


class FakeFresh:
    def __init__(self, *, deleted: bool, version: str = "v1") -> None:
        self.deleted = deleted
        self.version = version

    def list(self, resource, *, top=50, select=(), filter_expression=None):
        assert resource == "Catalog_Номенклатура"
        row = {
            "Ref_Key": PRODUCT_REF,
            "Code": "A-1",
            "Description": "Тестовый товар",
            "Единица": "шт",
            "DeletionMark": self.deleted,
            "DataVersion": self.version,
        }
        return [{key: value for key, value in row.items() if key in set(select)}]


class FakePrices:
    def __init__(self) -> None:
        self.calls = 0

    def product_prices(self, product_ref: str) -> ProductPrices:
        assert product_ref == PRODUCT_REF
        self.calls += 1
        return ProductPrices(retail=Decimal("100"), wholesale=Decimal("80"))


class FakeCeh:
    def __init__(self, archive_check=None) -> None:
        self.archive_check = archive_check or {
            "exists": True,
            "is_active": True,
            "total_stock": "0",
            "can_archive": True,
            "reason": None,
        }
        self.archive_checks = 0
        self.payloads = []

    def product_archive_check(self, external_ref):
        assert external_ref == PRODUCT_REF
        self.archive_checks += 1
        return dict(self.archive_check)

    def import_product(self, payload):
        self.payloads.append(dict(payload))
        return {"internal_id": "product-1", "repeated": False}


def config(policy: str, *, include_version: bool = True):
    product_fields = {
        "ref": "Ref_Key",
        "sku": "Code",
        "name": "Description",
        "unit_name": "Единица",
        "deletion_mark": "DeletionMark",
    }
    if include_version:
        product_fields["version"] = "DataVersion"
    return {
        **BASE,
        "product_deletion_policy": policy,
        "product_fields": product_fields,
    }


def importer(policy: str, *, deleted: bool, version: str = "v1", archive_check=None):
    data = config(policy)
    prices = FakePrices()
    ceh = FakeCeh(archive_check)
    service = FreshProductImporter(
        FakeFresh(deleted=deleted, version=version),  # type: ignore[arg-type]
        ceh,  # type: ignore[arg-type]
        TenantMapping.from_dict(data),
        ProductFieldMapping.from_dict(data),
        price_reader=prices,  # type: ignore[arg-type]
    )
    return service, ceh, prices


def test_deletion_policy_requires_marker_and_version_for_auto_archive():
    without_mark = {**BASE, "product_deletion_policy": "block", "product_fields": {"ref": "Ref_Key", "sku": "Code", "name": "Description"}}
    with pytest.raises(ValueError, match="deletion_mark"):
        ProductFieldMapping.from_dict(without_mark)

    with pytest.raises(ValueError, match="version"):
        ProductFieldMapping.from_dict(config("archive_if_zero_stock", include_version=False))


def test_ignore_never_deactivates_even_if_deletion_mark_field_is_present():
    service, ceh, prices = importer("ignore", deleted=True)
    summary = service.sync(execute=True)
    assert summary.imported == 1 and summary.blocked == 0 and summary.skipped == 0
    assert ceh.archive_checks == 0
    assert ceh.payloads[0]["is_active"] is True
    assert prices.calls == 1


def test_skip_and_block_do_not_write_deleted_product():
    skipped, skipped_ceh, skipped_prices = importer("skip", deleted=True)
    skipped_summary = skipped.sync(execute=True)
    assert skipped_summary.skipped == 1 and skipped_summary.imported == 0
    assert skipped_ceh.payloads == [] and skipped_prices.calls == 0

    blocked, blocked_ceh, blocked_prices = importer("block", deleted=True)
    blocked_summary = blocked.sync(execute=True)
    assert blocked_summary.blocked == 1 and blocked_summary.imported == 0
    assert "ручное решение" in blocked_summary.messages[0]
    assert blocked_ceh.payloads == [] and blocked_prices.calls == 0


def test_auto_archive_is_blocked_by_nonzero_stock_before_price_lookup():
    service, ceh, prices = importer(
        "archive_if_zero_stock",
        deleted=True,
        archive_check={
            "exists": True,
            "is_active": True,
            "total_stock": "3.000",
            "can_archive": False,
            "reason": "Нельзя архивировать товар с ненулевым остатком 3.000",
        },
    )
    summary = service.sync(execute=True)
    assert summary.blocked == 1 and summary.imported == 0
    assert ceh.archive_checks == 1 and ceh.payloads == []
    assert prices.calls == 0
    assert "ненулевым остатком" in summary.messages[0]


def test_auto_archive_and_reactivation_use_versioned_operation_keys():
    archived, archived_ceh, _ = importer("archive_if_zero_stock", deleted=True, version="v2")
    archive_plan = archived.plans()[0]
    assert archive_plan.payload is not None and archive_plan.payload["is_active"] is False
    archive_key = archive_plan.payload["operation_key"]
    archived.sync(execute=True)
    assert archived_ceh.payloads[0]["is_active"] is False

    active, _, _ = importer("archive_if_zero_stock", deleted=False, version="v3")
    active_plan = active.plans()[0]
    assert active_plan.payload is not None and active_plan.payload["is_active"] is True
    assert active_plan.payload["operation_key"] != archive_key


def test_auto_archive_skips_product_absent_from_ceh_sklad():
    service, ceh, prices = importer(
        "archive_if_zero_stock",
        deleted=True,
        archive_check={
            "exists": False,
            "is_active": None,
            "total_stock": "0",
            "can_archive": False,
            "reason": "Товар отсутствует",
        },
    )
    summary = service.sync(execute=True)
    assert summary.skipped == 1 and summary.blocked == 0 and summary.imported == 0
    assert ceh.archive_checks == 1 and ceh.payloads == []
    assert prices.calls == 0
