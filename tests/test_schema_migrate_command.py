from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest
from click.testing import CliRunner

from forecost.commands.ledger_cmd import _create_verified_backup, ledger
from forecost.ledger.db import get_ledger_db
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


def test_migration_backup_restores_exact_pre_migration_state(tmp_path):
    path = tmp_path / "ledger.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE sentinel(value TEXT NOT NULL);"
        "INSERT INTO sentinel VALUES ('pre-migration');"
        "PRAGMA user_version = 3;"
    )
    conn.close()

    migrated = CliRunner().invoke(ledger, ["migrate-schema", "--ledger-path", str(path)])
    backup = next(tmp_path.glob("ledger.db.pre-v*.bak"))
    restored = tmp_path / "restored.db"
    backup.replace(restored)
    checked = sqlite3.connect(restored)

    assert migrated.exit_code == 0, migrated.output
    assert checked.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert checked.execute("PRAGMA user_version").fetchone()[0] == 3
    assert checked.execute("SELECT value FROM sentinel").fetchone()[0] == "pre-migration"
    checked.close()


def test_backup_failure_removes_partial_image(tmp_path):
    path = tmp_path / "ledger.db"
    backup = tmp_path / "ledger.db.pre-v-test.bak"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sentinel(value TEXT)")
    conn.commit()

    class FaultingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql == "PRAGMA synchronous=FULL":
                raise sqlite3.OperationalError("injected backup fault")
            return super().execute(sql, parameters)

    def faulting_connect(destination: str) -> sqlite3.Connection:
        return sqlite3.connect(destination, factory=FaultingConnection)

    with pytest.raises(sqlite3.OperationalError, match="injected backup fault"):
        _create_verified_backup(conn, backup, connect=faulting_connect)
    conn.close()

    assert not backup.exists()


def test_sqlite_backup_captures_committed_concurrent_wal_pages(tmp_path):
    path = tmp_path / "ledger.db"
    backup = tmp_path / "backup.db"
    source = sqlite3.connect(path, check_same_thread=False)
    source.execute("PRAGMA journal_mode=WAL")
    source.execute("PRAGMA wal_autocheckpoint=0")
    source.execute("PRAGMA synchronous=FULL")
    source.execute("CREATE TABLE events(id INTEGER PRIMARY KEY, value TEXT)")
    source.commit()
    writer = sqlite3.connect(path, check_same_thread=False)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("PRAGMA synchronous=FULL")
    ready = threading.Event()

    def write_committed_wal_rows() -> None:
        writer.executemany(
            "INSERT INTO events(value) VALUES (?)", ((f"event-{index}",) for index in range(50))
        )
        writer.commit()
        ready.set()

    thread = threading.Thread(target=write_committed_wal_rows)
    thread.start()
    assert ready.wait(timeout=5)
    assert Path(f"{path}-wal").stat().st_size > 0

    _create_verified_backup(source, backup)
    thread.join(timeout=5)
    writer.close()
    source.close()
    restored = sqlite3.connect(backup)

    assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert restored.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 50
    restored.close()


def test_canonical_ledger_connections_use_full_synchronous(tmp_path):
    conn = get_ledger_db(tmp_path / "ledger.db")

    # SQLite represents FULL as integer level 2.
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2
    conn.close()
