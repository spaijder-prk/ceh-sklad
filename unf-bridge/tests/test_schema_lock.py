from __future__ import annotations

from copy import deepcopy

import pytest

from unf_bridge.evidence import metadata_structure_sha256
from unf_bridge.fresh_transport import FreshTransport
from unf_bridge.health import check_health
from unf_bridge.models import UnfProfile
from unf_bridge.odata import ODataEntitySet
from unf_bridge.snapshot_validate import validate_mapping_against_snapshot
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


def entity_sets() -> list[ODataEntitySet]:
    result: list[ODataEntitySet] = []
    for alias, name in BASE["resources"].items():
        if alias in BASE["external_key_fields"]:
            properties = ("Ref_Key", "Комментарий")
        elif alias == "prices":
            properties = ("Номенклатура_Key", "ВидЦен_Key", "Цена")
        else:
            properties = ("Ref_Key",)
        result.append(
            ODataEntitySet(
                name=name,
                entity_type=f"StandardODATA.{name}",
                properties=properties,
            )
        )
    return result


class FakeFresh:
    def entity_sets(self):
        return entity_sets()


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


def locked_mapping() -> TenantMapping:
    digest = metadata_structure_sha256(URL, entity_sets())
    payload = deepcopy(BASE)
    payload["expected_metadata_structure_sha256"] = digest.upper()
    return TenantMapping.from_dict(payload)


def test_schema_lock_normalizes_valid_sha256_and_rejects_invalid_value():
    mapping = locked_mapping()
    assert mapping.expected_metadata_structure_sha256 is not None
    assert mapping.expected_metadata_structure_sha256 == mapping.expected_metadata_structure_sha256.lower()

    payload = deepcopy(BASE)
    payload["expected_metadata_structure_sha256"] = "not-a-sha256"
    with pytest.raises(ValueError, match="expected_metadata_structure_sha256"):
        TenantMapping.from_dict(payload)


def test_transport_allows_discovery_without_lock_but_blocks_execute():
    transport = FreshTransport(FakeFresh(), TenantMapping.from_dict(BASE))  # type: ignore[arg-type]
    assert len(transport.validate_configuration()) == 64
    with pytest.raises(ValueError, match="Для записи в УНФ требуется"):
        transport.validate_configuration(require_schema_lock=True)


def test_transport_accepts_matching_lock_and_rejects_schema_drift():
    transport = FreshTransport(FakeFresh(), locked_mapping())  # type: ignore[arg-type]
    assert transport.validate_configuration(require_schema_lock=True) == (
        locked_mapping().expected_metadata_structure_sha256
    )

    payload = deepcopy(BASE)
    payload["expected_metadata_structure_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Schema lock УНФ"):
        FreshTransport(FakeFresh(), TenantMapping.from_dict(payload)).validate_configuration(  # type: ignore[arg-type]
            require_schema_lock=True
        )


def test_health_degrades_when_live_metadata_does_not_match_lock():
    payload = deepcopy(BASE)
    payload["expected_metadata_structure_sha256"] = "0" * 64
    health = check_health(
        FakeCeh(),  # type: ignore[arg-type]
        FakeFresh(),  # type: ignore[arg-type]
        TenantMapping.from_dict(payload),
    )
    assert health.status == "degraded"
    assert health.metadata_structure_matches_expected is False
    assert health.expected_metadata_structure_sha256 == "0" * 64

    ready = check_health(
        FakeCeh(),  # type: ignore[arg-type]
        FakeFresh(),  # type: ignore[arg-type]
        locked_mapping(),
    )
    assert ready.status == "ready"
    assert ready.metadata_structure_matches_expected is True


def test_offline_snapshot_validation_enforces_configured_schema_lock():
    mapping = locked_mapping()
    report = validate_mapping_against_snapshot(mapping, URL, entity_sets())
    assert report["metadata_structure_matches_expected"] is True
    assert report["metadata_structure_sha256"] == mapping.expected_metadata_structure_sha256

    payload = deepcopy(BASE)
    payload["expected_metadata_structure_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="expected_metadata_structure_sha256"):
        validate_mapping_against_snapshot(
            TenantMapping.from_dict(payload),
            URL,
            entity_sets(),
        )
