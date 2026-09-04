import pytest

from unf_bridge.odata import ODataEntitySet
from unf_bridge.snapshot_validate import sha256_file, validate_mapping_against_snapshot
from unf_bridge.tenant_config import TenantMapping


URL = "https://1cfresh.example/a/unf/100"

BASE = {
    "provider": "1cfresh",
    "application_url": URL,
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
        "cash_receipt": "Document_КассовыйДокумент",
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
    "reference_checks": [
        {
            "name": "cashbox",
            "resource": "Catalog_Кассы",
            "ref_key": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        }
    ],
}


def metadata_sets():
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
    result.append(
        ODataEntitySet(
            name="Catalog_Кассы",
            entity_type="StandardODATA.Catalog_Кассы",
            properties=("Ref_Key",),
        )
    )
    return result


def test_mapping_can_be_validated_offline_against_snapshot_model():
    mapping = TenantMapping.from_dict(BASE)
    report = validate_mapping_against_snapshot(mapping, URL, metadata_sets())

    assert report["status"] == "ready"
    assert report["entity_sets"] == len(metadata_sets())
    assert report["reference_checks"] == 1
    assert report["configured_resources"] == len(set(BASE["resources"].values()))


def test_offline_validation_rejects_snapshot_from_other_tenant():
    mapping = TenantMapping.from_dict(BASE)
    with pytest.raises(ValueError, match="application_url"):
        validate_mapping_against_snapshot(
            mapping,
            "https://1cfresh.example/a/other/999",
            metadata_sets(),
        )


def test_offline_validation_rejects_missing_reference_check_resource():
    mapping = TenantMapping.from_dict(BASE)
    sets = [item for item in metadata_sets() if item.name != "Catalog_Кассы"]
    with pytest.raises(ValueError, match="Catalog_Кассы"):
        validate_mapping_against_snapshot(mapping, URL, sets)


def test_sha256_file_is_stable_for_release_evidence(tmp_path):
    target = tmp_path / "evidence.json"
    target.write_bytes(b"abc")
    assert sha256_file(target) == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )
