from unf_bridge.health import check_health
from unf_bridge.models import UnfProfile
from unf_bridge.odata import ODataEntitySet
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


def test_health_reports_backend_schema_revision_when_ready():
    health = check_health(
        FakeCeh(),  # type: ignore[arg-type]
        FakeFresh(),  # type: ignore[arg-type]
        TenantMapping.from_dict(BASE),
        backend_readiness={
            "status": "ready",
            "database": "ok",
            "schema_revision": "20260904_09",
        },
    )
    assert health.status == "ready"
    assert health.backend_readiness_checked is True
    assert health.backend_ready is True
    assert health.backend_database == "ok"
    assert health.backend_schema_revision == "20260904_09"


def test_health_degraded_when_backend_readiness_is_not_ready():
    health = check_health(
        FakeCeh(),  # type: ignore[arg-type]
        FakeFresh(),  # type: ignore[arg-type]
        TenantMapping.from_dict(BASE),
        backend_readiness={
            "status": "not_ready",
            "database": "ok",
            "schema_revision": "20260904_09",
        },
    )
    assert health.status == "degraded"
    assert health.backend_readiness_checked is True
    assert health.backend_ready is False
