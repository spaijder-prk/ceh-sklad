from __future__ import annotations

from . import catalog_import, cli, fresh_probe, fresh_sync, location_import
from .remote_errors import guarded_remote_cli


@guarded_remote_cli
def bridge_main() -> None:
    cli.main()


@guarded_remote_cli
def fresh_probe_main() -> None:
    fresh_probe.main()


@guarded_remote_cli
def fresh_sync_main() -> None:
    fresh_sync.main()


@guarded_remote_cli
def import_products_main() -> None:
    catalog_import.main()


@guarded_remote_cli
def import_locations_main() -> None:
    location_import.main()
