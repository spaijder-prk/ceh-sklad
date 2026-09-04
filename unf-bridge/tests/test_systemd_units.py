from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SYSTEMD = ROOT / "deploy" / "systemd"

WRITING_SERVICES = {
    "ceh-unf-import-products.service",
    "ceh-unf-import-locations.service",
    "ceh-unf-sync.service",
}
ALL_SERVICES = WRITING_SERVICES | {"ceh-unf-health.service"}
TIMERS = {
    "ceh-unf-health.timer",
    "ceh-unf-import-products.timer",
    "ceh-unf-import-locations.timer",
    "ceh-unf-sync.timer",
}


def test_systemd_services_are_hardened_and_do_not_embed_secrets():
    for filename in ALL_SERVICES:
        text = (SYSTEMD / filename).read_text(encoding="utf-8")
        assert "User=ceh-unf" in text
        assert "Group=ceh-unf" in text
        assert "EnvironmentFile=/etc/ceh-sklad/unf-bridge.env" in text
        assert "StateDirectory=ceh-unf" in text
        assert "NoNewPrivileges=true" in text
        assert "ProtectSystem=strict" in text
        assert "ProtectHome=true" in text
        assert "StandardOutput=journal" in text
        assert "StandardError=journal" in text
        assert "UNF_FRESH_PASSWORD=" not in text
        assert "CEH_1C_KEY=" not in text


def test_writing_services_share_non_failing_exclusive_lock():
    lock = "/var/lib/ceh-unf/bridge.lock"
    for filename in WRITING_SERVICES:
        text = (SYSTEMD / filename).read_text(encoding="utf-8")
        assert f"/usr/bin/flock -n -E 0 {lock}" in text
        assert " --execute" in text


def test_health_unit_is_read_only_and_not_blocked_by_writer_lock():
    health = (SYSTEMD / "ceh-unf-health.service").read_text(encoding="utf-8")
    assert "ceh-unf-fresh-health" in health
    assert "--execute" not in health
    assert "/usr/bin/flock" not in health
    assert "/var/lib/ceh-unf/bridge.lock" not in health


def test_systemd_timers_are_persistent_and_target_matching_services():
    for filename in TIMERS:
        text = (SYSTEMD / filename).read_text(encoding="utf-8")
        expected_service = filename.removesuffix(".timer") + ".service"
        assert "Persistent=true" in text
        assert f"Unit={expected_service}" in text
        assert "WantedBy=timers.target" in text


def test_writing_units_target_expected_commands():
    product_import = (SYSTEMD / "ceh-unf-import-products.service").read_text(encoding="utf-8")
    location_import = (SYSTEMD / "ceh-unf-import-locations.service").read_text(encoding="utf-8")
    sync = (SYSTEMD / "ceh-unf-sync.service").read_text(encoding="utf-8")
    assert "ceh-unf-fresh-import-products" in product_import
    assert "ceh-unf-fresh-import-locations" in location_import
    assert "ceh-unf-fresh-sync" in sync
