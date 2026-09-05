import json

import pytest

from unf_bridge.fresh_probe import (
    SNAPSHOT_SCHEMA_VERSION,
    load_metadata_snapshot,
    metadata_snapshot,
    write_metadata_snapshot,
)
from unf_bridge.odata import ODataEntitySet, ODataField, ODataNavigation


def sample_entity_sets():
    document = ODataEntitySet(
        name="Document_РасходнаяНакладная",
        entity_type="StandardODATA.Document_РасходнаяНакладная",
        properties=("Ref_Key", "Комментарий"),
        fields=(
            ODataField("Ref_Key", "Edm.Guid", nullable=False),
            ODataField("Комментарий", "Edm.String", nullable=True),
        ),
        navigation=(
            ODataNavigation(
                "Запасы",
                "Collection(StandardODATA.Document_РасходнаяНакладная_Запасы_RowType)",
            ),
        ),
    )
    rows = ODataEntitySet(
        name="Document_РасходнаяНакладная_Запасы",
        entity_type="StandardODATA.Document_РасходнаяНакладная_Запасы_RowType",
        properties=("LineNumber", "Номенклатура_Key", "Количество"),
        fields=(
            ODataField("LineNumber", "Edm.Int32", nullable=False),
            ODataField("Номенклатура_Key", "Edm.Guid", nullable=False),
            ODataField("Количество", "Edm.Decimal", nullable=False),
        ),
    )
    return [document, rows]


def test_metadata_snapshot_contains_full_sanitized_schema():
    snapshot = metadata_snapshot(
        "https://1cfresh.example/a/unf/100/",
        sample_entity_sets(),
    )

    assert snapshot["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert snapshot["application_url"] == "https://1cfresh.example/a/unf/100"
    assert snapshot["entity_set_count"] == 2
    assert snapshot["entity_sets"][0]["name"] == "Document_РасходнаяНакладная"
    assert snapshot["entity_sets"][0]["fields"][0] == {
        "name": "Ref_Key",
        "edm_type": "Edm.Guid",
        "nullable": False,
    }
    assert snapshot["entity_sets"][0]["navigation"][0]["name"] == "Запасы"
    assert snapshot["entity_sets"][0]["related_entity_sets"] == [
        "Document_РасходнаяНакладная_Запасы"
    ]

    serialized = json.dumps(snapshot, ensure_ascii=False).casefold()
    assert "login" not in serialized
    assert "password" not in serialized
    assert "authorization" not in serialized


def test_snapshot_round_trip_restores_odata_model(tmp_path):
    target = tmp_path / "discovery" / "unf-metadata.json"
    write_metadata_snapshot(
        target,
        "https://1cfresh.example/a/unf/100",
        sample_entity_sets(),
    )

    application_url, entity_sets = load_metadata_snapshot(target)
    assert application_url == "https://1cfresh.example/a/unf/100"
    assert [item.name for item in entity_sets] == [
        "Document_РасходнаяНакладная",
        "Document_РасходнаяНакладная_Запасы",
    ]
    assert entity_sets[0].fields[0] == ODataField("Ref_Key", "Edm.Guid", False)
    assert entity_sets[0].navigation[0].name == "Запасы"
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_snapshot_loader_rejects_unknown_schema(tmp_path):
    target = tmp_path / "bad.json"
    target.write_text(
        json.dumps(
            {
                "schema_version": "unknown-v9",
                "application_url": "https://1cfresh.example/a/unf/100",
                "entity_sets": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Неподдерживаемая версия"):
        load_metadata_snapshot(target)
