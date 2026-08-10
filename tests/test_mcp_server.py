"""Contract tests for the canonical, read-only MCP surface."""

from __future__ import annotations

import json
import sqlite3

from forecost.lab import seed_demo
from forecost.mcp.server import (
    MCP_STORE_BOUNDARY,
    SUPPORTED_MCP_TOOLS,
    forecost_get_receipt,
    forecost_list_runs,
)


def test_supported_tools_are_canonical_and_read_only() -> None:
    assert SUPPORTED_MCP_TOOLS == ("forecost_list_runs", "forecost_get_receipt")
    assert "read-only" in MCP_STORE_BOUNDARY
    assert "cost_summary" not in SUPPORTED_MCP_TOOLS
    assert "forecast" not in SUPPORTED_MCP_TOOLS
    assert "track_call" not in SUPPORTED_MCP_TOOLS


def test_list_runs_is_versioned_and_reads_canonical_ledger(ledger_conn, monkeypatch) -> None:
    import forecost.mcp.server as server

    monkeypatch.setattr(server, "get_ledger_db", lambda: ledger_conn)
    run_id = seed_demo(ledger_conn, seed=71)

    payload = json.loads(forecost_list_runs())

    assert payload["schema_version"] == 1
    assert payload["store"] == MCP_STORE_BOUNDARY
    assert payload["runs"][0]["run_id"] == run_id
    assert payload["runs"][0]["evidence_state"] == "complete"


def test_receipt_is_versioned_and_matches_canonical_receipt(ledger_conn, monkeypatch) -> None:
    import forecost.mcp.server as server

    monkeypatch.setattr(server, "get_ledger_db", lambda: ledger_conn)
    run_id = seed_demo(ledger_conn, seed=73)

    payload = json.loads(forecost_get_receipt(run_id))

    assert payload["schema_version"] == 1
    assert payload["store"] == MCP_STORE_BOUNDARY
    assert payload["receipt"]["run_id"] == run_id
    assert payload["receipt"]["evidence"]["state"] == "complete"


def test_unknown_run_returns_machine_readable_error(ledger_conn, monkeypatch) -> None:
    import forecost.mcp.server as server

    monkeypatch.setattr(server, "get_ledger_db", lambda: ledger_conn)

    payload = json.loads(forecost_get_receipt("missing"))

    assert payload["error"]["code"] == "unknown-run"
    assert "forecost_list_runs" in payload["error"]["hint"]


def test_invalid_limits_do_not_touch_the_database(monkeypatch) -> None:
    import forecost.mcp.server as server

    def fail_if_called():
        raise AssertionError("database should not be opened")

    monkeypatch.setattr(server, "get_ledger_db", fail_if_called)
    payload = json.loads(forecost_list_runs(limit=0))
    assert payload["error"]["code"] == "invalid-limit"


def test_database_failures_are_bounded_machine_readable_errors(monkeypatch) -> None:
    import forecost.mcp.server as server

    def broken_database():
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(server, "get_ledger_db", broken_database)
    payload = json.loads(forecost_list_runs())
    assert payload["error"] == {"code": "ledger-database", "message": "disk I/O error"}
