from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP = REPO_ROOT / "scripts" / "backup.sh"
RESTORE = REPO_ROOT / "scripts" / "restore.sh"


class BackupRestoreContractTests(unittest.TestCase):
    def test_backup_supports_production_compose_and_private_files(self) -> None:
        script = BACKUP.read_text(encoding="utf-8")
        self.assertIn("--production", script)
        self.assertIn(".env.production", script)
        self.assertIn("docker-compose.production.yml", script)
        self.assertIn("umask 077", script)
        self.assertIn('docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE"', script)

    def test_restore_supports_same_production_context(self) -> None:
        script = RESTORE.read_text(encoding="utf-8")
        self.assertIn("--production", script)
        self.assertIn(".env.production", script)
        self.assertIn("docker-compose.production.yml", script)
        self.assertIn('docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE"', script)
        self.assertIn("pg_restore", script)
        self.assertIn("stop backend", script)
        self.assertIn("start backend", script)


if __name__ == "__main__":
    unittest.main()
