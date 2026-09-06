from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_backup_validates_archive_and_writes_checksum():
    script = (ROOT / "scripts/backup.sh").read_text(encoding="utf-8")

    assert "pg_restore --list" in script
    assert "sha256sum" in script
    assert "schema_revision" in script
    assert "BACKUP_FILE=" in script


def test_caddy_pki_backup_preserves_private_ca_for_disaster_recovery():
    script = (ROOT / "scripts/backup_caddy_pki.sh").read_text(encoding="utf-8")

    assert "caddy/pki" in script
    assert "root.crt" in script
    assert "root.key" in script
    assert "sha256sum" in script
    assert "umask 077" in script
    assert "private key" in script


def test_offsite_backup_requires_external_destination():
    script = (ROOT / "scripts/backup_offsite.sh").read_text(encoding="utf-8")

    assert "CEH_BACKUP_OFFSITE_DIR" in script
    assert "CEH_BACKUP_RCLONE_REMOTE" in script
    assert "rclone copyto" in script
    assert "sha256sum -c" in script


def test_backup_and_monitor_have_persistent_systemd_timers():
    backup_timer = (ROOT / "deploy/systemd/ceh-backup.timer").read_text(encoding="utf-8")
    monitor_timer = (ROOT / "deploy/systemd/ceh-monitor.timer").read_text(encoding="utf-8")

    assert "OnCalendar=" in backup_timer
    assert "Persistent=true" in backup_timer
    assert "OnUnitActiveSec=5m" in monitor_timer
    assert "Persistent=true" in monitor_timer


def test_production_monitor_checks_ready_backup_disk_and_internal_ca():
    script = (ROOT / "scripts/production_monitor.py").read_text(encoding="utf-8")
    service = (ROOT / "deploy/systemd/ceh-monitor.service").read_text(encoding="utf-8")

    assert "/health/ready" in script
    assert "sha256" in script
    assert "disk_usage" in script
    assert "CEH_MONITOR_WEBHOOK_URL" in script
    assert "CEH_MONITOR_CA_CERT" in script
    assert "CEH_MONITOR_CONNECT_HOST" in script
    assert "ssl.create_default_context" in script
    assert "Environment=CEH_MONITOR_CA_CERT=/etc/ceh-sklad/ceh-sklad-root-ca.crt" in service
    assert "Environment=CEH_MONITOR_CONNECT_HOST=127.0.0.1" in service
