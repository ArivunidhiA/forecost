"""Tests for `forecost migrate` (legacy costs.db -> ledger)."""

import sqlite3

from click.testing import CliRunner

from forecost.cli import main
from forecost.commands.migrate_cmd import _legacy_rows, _parse_ts
from forecost.ledger.db import get_ledger_db


def _make_legacy_db(path):
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, path TEXT);
        CREATE TABLE usage_logs (
            id INTEGER PRIMARY KEY, project_id INTEGER, timestamp TEXT, model TEXT,
            provider TEXT, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL
        );
        INSERT INTO projects VALUES (1, 'proj', '/tmp/proj');
        INSERT INTO usage_logs VALUES
            (1, 1, '2026-03-01T00:00:00+00:00', 'claude-opus-4-8', 'anthropic', 1000000, 0, 99.0),
            (2, 1, '2026-03-02T00:00:00+00:00', 'claude-opus-4-8', 'anthropic', 0, 1000000, 99.0);
        """
    )
    conn.commit()
    conn.close()


def test_migrate_ports_and_reprices(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    from forecost.ledger import db as ledger_db

    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "ledger.db")
    ledger_db.reset_connection_for_tests()

    _make_legacy_db(tmp_path / "costs.db")

    result = CliRunner().invoke(main, ["migrate"])
    assert result.exit_code == 0, result.output
    assert "Migrated 2 legacy usage row(s)" in result.output

    conn = get_ledger_db()
    n = conn.execute("SELECT COUNT(*) FROM usage_events WHERE source='legacy-costs-db'").fetchone()[
        0
    ]
    assert n == 2
    # Re-priced with the CURRENT table: opus-4-8 input $5/MTok, output $25/MTok.
    total = conn.execute("SELECT SUM(amount) FROM postings WHERE basis='pricing_table'").fetchone()[
        0
    ]
    assert abs(total - (5.0 + 25.0)) < 0.01  # NOT the legacy 99+99

    # Idempotent second run.
    result2 = CliRunner().invoke(main, ["migrate"])
    assert "Migrated 0 legacy usage row(s)" in result2.output
    ledger_db.reset_connection_for_tests()


def test_migrate_no_legacy_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    result = CliRunner().invoke(main, ["migrate"])
    assert result.exit_code == 0
    assert "No legacy costs.db" in result.output


def test_migrate_skips_malformed_timestamp_instead_of_fabricating_now(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    from forecost.ledger import db as ledger_db

    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "ledger.db")
    ledger_db.reset_connection_for_tests()
    _make_legacy_db(tmp_path / "costs.db")
    conn = sqlite3.connect(tmp_path / "costs.db")
    conn.execute(
        "INSERT INTO usage_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (3, 1, "not-a-timestamp", "claude-opus-4-8", "anthropic", 10, 20, 0.1),
    )
    conn.commit()
    conn.close()

    result = CliRunner().invoke(main, ["migrate"])

    assert result.exit_code == 0, result.output
    assert "1 skipped: invalid timestamp" in result.output
    ledger = get_ledger_db()
    assert ledger.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 2
    assert (
        ledger.execute("SELECT COUNT(*) FROM usage_events WHERE event_uid='legacy:3'").fetchone()[0]
        == 0
    )
    ledger_db.reset_connection_for_tests()


def test_parse_ts_treats_naive_legacy_timestamp_as_utc():
    parsed = _parse_ts("2026-03-01T12:34:56")

    assert parsed is not None
    assert parsed.isoformat() == "2026-03-01T12:34:56+00:00"


def test_legacy_rows_tolerates_missing_projects_table(tmp_path):
    costs_db = tmp_path / "costs.db"
    conn = sqlite3.connect(costs_db)
    conn.execute(
        """
        CREATE TABLE usage_logs (
            id INTEGER PRIMARY KEY, project_id INTEGER, timestamp TEXT, model TEXT,
            provider TEXT, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL
        )
        """
    )
    conn.execute("INSERT INTO usage_logs VALUES (1, 99, '2026-03-01T00:00:00Z', 'm', 'p', 1, 2, 3)")
    conn.commit()
    conn.close()

    rows, projects = _legacy_rows(costs_db)

    assert len(rows) == 1
    assert projects == {}


def test_migrate_reports_unreadable_legacy_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    (tmp_path / "costs.db").write_text("not a sqlite database")

    result = CliRunner().invoke(main, ["migrate"])

    assert result.exit_code == 0
    assert "Could not read legacy costs.db" in result.output


def test_migrate_reports_empty_usage_table(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    conn = sqlite3.connect(tmp_path / "costs.db")
    conn.executescript(
        """
        CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, path TEXT);
        CREATE TABLE usage_logs (
            id INTEGER PRIMARY KEY, project_id INTEGER, timestamp TEXT, model TEXT,
            provider TEXT, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL
        );
        """
    )
    conn.close()

    result = CliRunner().invoke(main, ["migrate"])

    assert result.exit_code == 0
    assert "has no usage rows" in result.output
