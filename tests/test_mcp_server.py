"""Contract tests for the canonical, read-only MCP surface."""

from __future__ import annotations

import json
import sqlite3

from forecost.lab import seed_demo
from forecost.mcp.server import (
    MCP_STORE_BOUNDARY,
    SUPPORTED_MCP_TOOLS,
    forecost_compare_runs,
    forecost_get_receipt,
    forecost_list_runs,
)


def test_supported_tools_are_canonical_and_read_only() -> None:
    assert SUPPORTED_MCP_TOOLS == (
        "forecost_list_runs",
        "forecost_get_receipt",
        "forecost_compare_runs",
    )
    assert "read-only" in MCP_STORE_BOUNDARY
    assert "cost_summary" not in SUPPORTED_MCP_TOOLS
    assert "forecast" not in SUPPORTED_MCP_TOOLS
    assert "track_call" not in SUPPORTED_MCP_TOOLS


def test_list_runs_is_versioned_and_reads_canonical_ledger(ledger_conn, monkeypatch) -> None:
    import forecost.mcp.server as server

    monkeypatch.setattr(server, "get_readonly_ledger_db", lambda: ledger_conn)
    run_id = seed_demo(ledger_conn, seed=71)

    payload = json.loads(forecost_list_runs())

    assert payload["schema_version"] == 1
    assert payload["store"] == MCP_STORE_BOUNDARY
    assert payload["runs"][0]["run_id"] == run_id
    profiles = payload["runs"][0]["evidence_profiles"]
    assert profiles["structural"]["completeness"] == "complete"
    assert profiles["provider-billed"]["completeness"] == "partial"


def test_receipt_is_versioned_and_matches_canonical_receipt(ledger_conn, monkeypatch) -> None:
    import forecost.mcp.server as server

    monkeypatch.setattr(server, "get_readonly_ledger_db", lambda: ledger_conn)
    run_id = seed_demo(ledger_conn, seed=73)

    payload = json.loads(forecost_get_receipt(run_id))

    assert payload["schema_version"] == 1
    assert payload["store"] == MCP_STORE_BOUNDARY
    assert payload["receipt"]["run_id"] == run_id
    evidence = payload["receipt"]["evidence"]
    assert "state" not in evidence
    assert evidence["claim_profiles"]["structural"]["completeness"] == "complete"
    assert evidence["claim_profiles"]["provider-billed"]["completeness"] == "partial"


def test_unknown_run_returns_machine_readable_error(ledger_conn, monkeypatch) -> None:
    import forecost.mcp.server as server

    monkeypatch.setattr(server, "get_readonly_ledger_db", lambda: ledger_conn)

    payload = json.loads(forecost_get_receipt("missing"))

    assert payload["error"]["code"] == "unknown-run"
    assert "forecost_list_runs" in payload["error"]["hint"]


def test_existing_run_with_malformed_evidence_is_not_reported_as_unknown(
    ledger_conn, monkeypatch
) -> None:
    import forecost.mcp.server as server

    monkeypatch.setattr(server, "get_readonly_ledger_db", lambda: ledger_conn)
    run_id = seed_demo(ledger_conn, seed=75)
    row = ledger_conn.execute(
        "SELECT c.charge_id, c.tariff_json FROM charges c JOIN causal_spans s "
        "ON s.span_key = c.span_key WHERE s.run_id = ? LIMIT 1",
        (run_id,),
    ).fetchone()
    assert row is not None
    ledger_conn.execute(
        "UPDATE charges SET tariff_json = ? WHERE charge_id = ?",
        ("not-json", row["charge_id"]),
    )
    ledger_conn.commit()
    payload = json.loads(forecost_get_receipt(run_id))

    assert payload["error"]["code"] == "receipt-evidence"


def test_invalid_limits_do_not_touch_the_database(monkeypatch) -> None:
    import forecost.mcp.server as server

    def fail_if_called():
        raise AssertionError("database should not be opened")

    monkeypatch.setattr(server, "get_readonly_ledger_db", fail_if_called)
    payload = json.loads(forecost_list_runs(limit=0))
    assert payload["error"]["code"] == "invalid-limit"


def test_database_failures_are_bounded_machine_readable_errors(monkeypatch) -> None:
    import forecost.mcp.server as server

    def broken_database():
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(server, "get_readonly_ledger_db", broken_database)
    payload = json.loads(forecost_list_runs())
    assert payload["error"] == {"code": "ledger-database", "message": "disk I/O error"}


def test_compare_runs_is_read_only_and_refuses_to_infer_pairing(ledger_conn, monkeypatch) -> None:
    import forecost.mcp.server as server

    monkeypatch.setattr(server, "get_readonly_ledger_db", lambda: ledger_conn)
    baseline = seed_demo(ledger_conn, seed=79)
    candidate = seed_demo(ledger_conn, seed=83)

    payload = json.loads(forecost_compare_runs(baseline, candidate))

    assert payload["schema_version"] == 1
    assert payload["store"] == MCP_STORE_BOUNDARY
    comparison = payload["comparison"]
    assert comparison["decision"]["status"] == "abstain"
    assert "COMPARISON_MANIFEST_REQUIRED" in comparison["decision"]["reason_codes"]
    assert comparison["scope"]["authority"] == "list_rate"


def test_compare_runs_rejects_unsupported_scope_without_opening_ledger(monkeypatch) -> None:
    import forecost.mcp.server as server

    def fail_if_called():
        raise AssertionError("database should not be opened")

    monkeypatch.setattr(server, "get_readonly_ledger_db", fail_if_called)

    authority = json.loads(forecost_compare_runs("a", "b", authority="billed"))
    currency = json.loads(forecost_compare_runs("a", "b", currency="EUR"))

    assert authority["error"]["code"] == "unsupported-authority"
    assert currency["error"]["code"] == "unsupported-currency"


def test_compare_runs_returns_bounded_error_for_unsafe_identifier(monkeypatch) -> None:
    import forecost.mcp.server as server

    def fail_if_called():
        raise AssertionError("database should not be opened")

    monkeypatch.setattr(server, "get_readonly_ledger_db", fail_if_called)

    payload = json.loads(forecost_compare_runs("contains a space", "candidate"))

    assert payload["error"]["code"] == "invalid-baseline-run-id"
    assert "identifier" in payload["error"]["message"]
