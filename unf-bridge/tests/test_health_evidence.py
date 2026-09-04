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
                properties = ("Комментарий",)
            elif alias == "prices":
                properties = ("Номенклатура_Key", "ВидЦен_Key", "Цена")
            else:
                properties = ()
            result.append(
                ODataEntitySet(
                    name=name,
                    entity_type=f"StandardODATA.{name}",
                    properties=properties,
                )
            )
        return result


def test_health_exposes_mapping_and_metadata_evidence():
    health = check_health(
        FakeCeh(),  # type: ignore[arg-type]
        FakeFresh(),  # type: ignore[arg-type]
        TenantMapping.from_dict(BASE),
        mapping_sha256="a" * 64,
    )

    assert health.status == "ready"
    assert health.mapping_sha256 == "a" * 64
    assert len(health.metadata_structure_sha256) == 64
