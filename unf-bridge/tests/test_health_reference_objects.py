from unf_bridge.health import check_health
from unf_bridge.models import UnfProfile
from unf_bridge.odata import ODataEntitySet
from unf_bridge.tenant_audit import TenantAuditReport
from unf_bridge.tenant_config import TenantMapping


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
        "organization_ref": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "retail_customer_ref": "dddddddd-dddd-dddd-dddd-dddddddddddd",
        "wholesale_customer_ref": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    },
}


class FakeCeh:
    def profile(self):
        return UnfProfile(
            contract_version="unf-cloud-v2",
            target_configuration="1С:Управление нашей фирмой",
            deployment="cloud",
            confirm_export_path="/confirm",
            confirm_export_batch_path="/confirm-batch",
        )

    def outbox(self, limit=100):
        return []


class FakeFresh:
    def __init__(self, missing_ref: str | None = None):
        self.missing_ref = missing_ref
        self.queries = []

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

    def find_one_by_guid(self, resource, ref_key):
        self.queries.append((resource, ref_key))
        if ref_key == self.missing_ref:
            return None
        return {"Ref_Key": ref_key}


def audit_ready():
    return TenantAuditReport(
        status="ready",
        errors=(),
        warnings=(),
        payload_schema_count=5,
        location_allowlist_count=2,
        representative_count=1,
        payer_mapping_count=1,
        post_documents=False,
    )


def test_health_validates_known_reference_constants_read_only():
    fresh = FakeFresh()
    health = check_health(
        FakeCeh(),  # type: ignore[arg-type]
        fresh,  # type: ignore[arg-type]
        TenantMapping.from_dict(BASE),
        mapping_audit=audit_ready(),
        validate_reference_objects=True,
    )
    assert health.reference_objects_ready is True
    assert health.reference_validation_errors == ()
    assert len(fresh.queries) == 5


def test_health_degraded_when_configured_customer_ref_does_not_exist():
    missing = BASE["constants"]["wholesale_customer_ref"]
    health = check_health(
        FakeCeh(),  # type: ignore[arg-type]
        FakeFresh(missing),  # type: ignore[arg-type]
        TenantMapping.from_dict(BASE),
        mapping_audit=audit_ready(),
        validate_reference_objects=True,
    )
    assert health.status == "degraded"
    assert health.reference_objects_ready is False
    assert len(health.reference_validation_errors) == 1
    assert "wholesale_customer_ref" in health.reference_validation_errors[0]
    assert missing in health.reference_validation_errors[0]
