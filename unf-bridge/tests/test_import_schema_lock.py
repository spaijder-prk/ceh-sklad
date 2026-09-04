from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_both_automatic_import_commands_require_schema_lock_on_execute():
    for relative in (
        "unf-bridge/unf_bridge/catalog_import.py",
        "unf-bridge/unf_bridge/location_import.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "validate_metadata_schema_lock(" in source
        assert "require_schema_lock=args.execute" in source


def test_outbound_transport_uses_the_same_shared_schema_lock_helper():
    source = (ROOT / "unf-bridge/unf_bridge/fresh_transport.py").read_text(encoding="utf-8")
    assert "from .schema_lock import validate_metadata_schema_lock" in source
    assert "validate_metadata_schema_lock(" in source
