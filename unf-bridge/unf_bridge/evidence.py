from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .fresh_probe import metadata_snapshot
from .odata import ODataEntitySet


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def metadata_structure_sha256(
    application_url: str,
    entity_sets: list[ODataEntitySet],
) -> str:
    """SHA-256 канонической структуры OData без credentials и HTTP headers."""
    ordered = sorted(entity_sets, key=lambda item: item.name.casefold())
    payload = json.dumps(
        metadata_snapshot(application_url, ordered),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
