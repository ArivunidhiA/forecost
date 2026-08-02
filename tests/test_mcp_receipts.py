from __future__ import annotations

import json

from forecost.lab import seed_demo
from forecost.mcp.server import forecost_get_receipt, forecost_list_runs


def test_mcp_receipt_tools_use_canonical_ledger(ledger_conn, monkeypatch):
    import forecost.mcp.server as server

    monkeypatch.setattr(server, "get_ledger_db", lambda: ledger_conn)
    run_id = seed_demo(ledger_conn, seed=71)

    listed = json.loads(forecost_list_runs())
    receipt = json.loads(forecost_get_receipt(run_id))

    assert listed[0]["run_id"] == run_id
    assert listed[0]["evidence_state"] == "complete"
    assert receipt["run_id"] == run_id
    assert receipt["evidence"]["state"] == "complete"


def test_mcp_receipt_tool_rejects_unknown_run(ledger_conn, monkeypatch):
    import forecost.mcp.server as server

    monkeypatch.setattr(server, "get_ledger_db", lambda: ledger_conn)

    assert "Use forecost_list_runs" in forecost_get_receipt("missing")
