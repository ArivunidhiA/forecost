from __future__ import annotations

import sqlite3

from click.testing import CliRunner

from forecost.commands.ledger_cmd import ledger
from forecost.ledger.schema import SCHEMA_VERSION


def test_schema_migration_dry_run_and_backup(tmp_path):
    path = tmp_path / "ledger.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()
    runner = CliRunner()

    dry = runner.invoke(ledger, ["migrate-schema", "--ledger-path", str(path), "--dry-run"])
    migrated = runner.invoke(ledger, ["migrate-schema", "--ledger-path", str(path)])

    assert dry.exit_code == 0
    assert "no changes made" in dry.output
    assert migrated.exit_code == 0
    assert "backup:" in migrated.output
    assert list(tmp_path.glob("ledger.db.pre-v*.bak"))
    checked = sqlite3.connect(path)
    assert checked.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    checked.close()
