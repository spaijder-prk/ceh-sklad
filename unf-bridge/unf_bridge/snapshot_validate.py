from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .fresh_probe import SNAPSHOT_SCHEMA_VERSION, load_metadata_snapshot
from .odata import ODataEntitySet
from .tenant_config import TenantMapping


def validate_mapping_against_snapshot(
    mapping: TenantMapping,
    snapshot_application_url: str,
    entity_sets: list[ODataEntitySet],
) -> dict[str, Any]:
    if mapping.application_url.rstrip("/") != snapshot_application_url.rstrip("/"):
        raise ValueError(
            "application_url в mapping не совпадает с application_url metadata snapshot"
        )
    mapping.validate_against_metadata(entity_sets)
    return {
        "status": "ready",
        "snapshot_schema": SNAPSHOT_SCHEMA_VERSION,
        "application_url": snapshot_application_url.rstrip("/"),
        "entity_sets": len(entity_sets),
        "configured_resources": len(set(mapping.resources.values())),
        "payload_schemas": len(mapping.payload_schemas),
        "reference_checks": len(mapping.reference_checks),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline-проверка tenant mapping по сохраненному metadata snapshot УНФ"
    )
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        mapping = TenantMapping.load(args.mapping)
        snapshot_url, entity_sets = load_metadata_snapshot(args.snapshot)
        report = validate_mapping_against_snapshot(mapping, snapshot_url, entity_sets)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error": str(exc),
                    "snapshot_schema": SNAPSHOT_SCHEMA_VERSION,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        sys.exit(3)

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
