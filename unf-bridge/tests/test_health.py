from decimal import Decimal

from unf_bridge.catalog_import import ProductFieldMapping
from unf_bridge.health import check_health
from unf_bridge.location_import import LocationImportMapping
from unf_bridge.models import UnfLine, UnfOutboxItem, UnfProfile
from unf_bridge.odata import ODataEntitySet
from unf_bridge.tenant_audit import TenantAuditReport
from unf_bridge.tenant_config import TenantMapping


WAREHOUSE = "11111111-1111-1111-1111-111111111111"
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


class FakeCeh:
    def __init__(self, items):
        self.items = items

    def profile(self):
        return UnfProfile(
            contract_version="unf-cloud-v2",
            target_configuration="1С:Управление нашей фирмой",
            deployment="cloud",
            confirm_export_path="/confirm",
            confirm_export_batch_path="/confirm-batch",
        )

    def outbox(self, limit=100):
        return self.items[:limit]


class FakeFresh:
    def entity_sets(self):
        result = []
        for alias, name in BASE["resources"].items():
            if alias in BASE["external_key_fields"]:
                props = ("Комментарий",)
            elif alias == "prices":
                props = ("Номенклатура_Key", "ВидЦен_Key", "Цена")
            else:
                props = ()
            result.append(ODataEntitySet(name=name, entity_type=f"StandardODATA.{name}", properties=props))
        return result


class FakeFreshCatalogFields(FakeFresh):
    def entity_sets(self):
        rows = super().entity_sets()
        result = []
        for row in rows:
            if row.name == BASE["resources"]["products"]:
                result.append(
                    ODataEntitySet(
                        name=row.name,
                        entity_type=row.entity_type,
                        properties=("Ref_Key", "Артикул", "Description", "Единица"),
                    )
                )
            elif row.name == BASE["resources"]["warehouses"]:
                result.append(
                    ODataEntitySet(
                        name=row.name,
                        entity_type=row.entity_type,
                        properties=("Ref_Key", "Description"),
                    )
                )
            else:
                result.append(row)
        return result


def item(*, ready=True):
    return UnfOutboxItem(
        entity_type="stock_document",
        internal_id="doc-1",
        kind="transfer",
        unf_document="Перемещение запасов",
        unf_operation="Перемещение",
        ready_for_unf=ready,
        blocking_reasons=() if ready else ("Не сопоставлен склад",),
        requires_split=False,
        source_location_external_1c_id="source",
        destination_location_external_1c_id="destination",
        adjustment_location_external_1c_id=None,
        representative_external_1c_id=None,
        amount=None,
        comment=None,
        lines=(
            UnfLine(
                product_external_1c_id="product",
                sku="SKU",
                quantity=Decimal("1"),
                quantity_delta=None,
                unit_price=None,
            ),
        ),
    )


def audit(status="ready") -> TenantAuditReport:
    return TenantAuditReport(
        status=status,
        errors=() if status == "ready" else ("Не задан constants.cashbox_ref",),
        warnings=("post_documents=false",),
        payload_schema_count=5,
        location_allowlist_count=2,
        representative_count=1,
        payer_mapping_count=1,
        post_documents=False,
    )


def test_health_ready_is_read_only_summary_without_explicit_static_audit():
    health = check_health(
        FakeCeh([item()]),  # type: ignore[arg-type]
        FakeFresh(),  # type: ignore[arg-type]
        TenantMapping.from_dict(BASE),
    )
    assert health.status == "ready"
    assert health.outbox_items == 1
    assert health.ready_items == 1
    assert health.blocked_items == 0
    assert health.planned_documents == 1
    assert health.payload_validated_documents == 0
    assert health.payload_validation_errors == ()
    assert health.catalog_mapping_ready is True
    assert health.catalog_mapping_errors == ()
    assert health.published_entity_sets == len(BASE["resources"])
    assert health.mapping_audit_ready is True


def test_health_degraded_when_outbox_contains_blocked_item():
    health = check_health(
        FakeCeh([item(ready=False)]),  # type: ignore[arg-type]
        FakeFresh(),  # type: ignore[arg-type]
        TenantMapping.from_dict(BASE),
    )
    assert health.status == "degraded"
    assert health.blocked_items == 1
    assert health.ready_items == 0


def test_health_degraded_when_static_tenant_audit_is_blocked():
    health = check_health(
        FakeCeh([item()]),  # type: ignore[arg-type]
        FakeFresh(),  # type: ignore[arg-type]
        TenantMapping.from_dict(BASE),
        mapping_audit=audit("blocked"),
    )
    assert health.status == "degraded"
    assert health.blocked_items == 0
    assert health.mapping_audit_ready is False
    assert health.mapping_audit_errors == ("Не задан constants.cashbox_ref",)
    assert health.mapping_audit_warnings == ("post_documents=false",)


def test_health_degraded_when_ready_outbox_cannot_build_payload():
    health = check_health(
        FakeCeh([item()]),  # type: ignore[arg-type]
        FakeFresh(),  # type: ignore[arg-type]
        TenantMapping.from_dict(BASE),
        mapping_audit=audit("ready"),
    )
    assert health.status == "degraded"
    assert health.ready_items == 0
    assert health.blocked_items == 1
    assert health.planned_documents == 1
    assert health.payload_validated_documents == 0
    assert len(health.payload_validation_errors) == 1
    assert "doc-1" in health.payload_validation_errors[0]
    assert "payload_schemas" in health.payload_validation_errors[0]


def test_health_degraded_when_catalog_import_field_is_absent_from_metadata():
    product_mapping = ProductFieldMapping.from_dict(
        {"product_fields": {"ref": "MissingRef", "sku": "Артикул", "name": "Description"}}
    )
    location_mapping = LocationImportMapping.from_dict(
        {
            "location_fields": {"ref": "Ref_Key", "name": "Description"},
            "location_allowlist": {WAREHOUSE: {"kind": "warehouse"}},
        }
    )
    health = check_health(
        FakeCeh([]),  # type: ignore[arg-type]
        FakeFreshCatalogFields(),  # type: ignore[arg-type]
        TenantMapping.from_dict(BASE),
        product_mapping=product_mapping,
        location_mapping=location_mapping,
    )
    assert health.status == "degraded"
    assert health.catalog_mapping_ready is False
    assert len(health.catalog_mapping_errors) == 1
    assert "products:" in health.catalog_mapping_errors[0]
    assert "MissingRef" in health.catalog_mapping_errors[0]
