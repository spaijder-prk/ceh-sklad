from __future__ import annotations

from .evidence import metadata_structure_sha256
from .odata import ODataEntitySet


def validate_metadata_schema_lock(
    application_url: str,
    entity_sets: list[ODataEntitySet],
    expected_digest: str | None,
    *,
    require_schema_lock: bool = False,
) -> str:
    """Проверяет канонический digest live metadata перед любой автоматической записью."""
    current_digest = metadata_structure_sha256(application_url, entity_sets)
    if expected_digest is not None and expected_digest != current_digest:
        raise ValueError(
            "Schema lock УНФ не совпадает с текущей $metadata: "
            f"ожидался {expected_digest}, получен {current_digest}"
        )
    if require_schema_lock and expected_digest is None:
        raise ValueError(
            "Для автоматической записи требуется expected_metadata_structure_sha256 "
            "из принятого metadata snapshot"
        )
    return current_digest
