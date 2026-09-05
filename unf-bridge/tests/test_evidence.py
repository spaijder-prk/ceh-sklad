from unf_bridge.evidence import metadata_structure_sha256
from unf_bridge.odata import ODataEntitySet, ODataField


URL = "https://1cfresh.example/a/unf/100"


def test_metadata_structure_sha256_is_order_independent():
    first = ODataEntitySet(
        name="Catalog_Товары",
        entity_type="StandardODATA.Catalog_Товары",
        properties=("Ref_Key", "Description"),
        fields=(
            ODataField("Ref_Key", "Edm.Guid", False),
            ODataField("Description", "Edm.String", True),
        ),
    )
    second = ODataEntitySet(
        name="Catalog_Склады",
        entity_type="StandardODATA.Catalog_Склады",
        properties=("Ref_Key",),
        fields=(ODataField("Ref_Key", "Edm.Guid", False),),
    )

    direct = metadata_structure_sha256(URL, [first, second])
    reversed_digest = metadata_structure_sha256(URL, [second, first])

    assert direct == reversed_digest
    assert len(direct) == 64


def test_metadata_structure_sha256_changes_when_schema_changes():
    before = ODataEntitySet(
        name="Catalog_Товары",
        entity_type="StandardODATA.Catalog_Товары",
        properties=("Ref_Key",),
        fields=(ODataField("Ref_Key", "Edm.Guid", False),),
    )
    after = ODataEntitySet(
        name="Catalog_Товары",
        entity_type="StandardODATA.Catalog_Товары",
        properties=("Ref_Key", "Description"),
        fields=(
            ODataField("Ref_Key", "Edm.Guid", False),
            ODataField("Description", "Edm.String", True),
        ),
    )

    assert metadata_structure_sha256(URL, [before]) != metadata_structure_sha256(URL, [after])
