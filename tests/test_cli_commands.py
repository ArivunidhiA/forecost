"""Tests for the new ledger-era CLI commands via click's CliRunner.

Each test points HOME at a tmp dir and resets the cached ledger connection so the
commands operate on an isolated ledger.db, then asserts on stdout.
"""

import json
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

import forecost.ledger.db as ledger_db
from forecost.adapters.base import Money, UsageEvent
from forecost.commands.burn_cmd import burn
from forecost.commands.calibration_cmd import calibration
from forecost.commands.ingest_cmd import ingest
from forecost.commands.ledger_cmd import ledger
from forecost.commands.pricing_audit_cmd import pricing_audit
from forecost.commands.reconcile_cmd import reconcile
from forecost.ledger.sink import SyncLedgerSink


@pytest.fixture
def isolated_ledger(tmp_path, monkeypatch):
    path = tmp_path / "ledger.db"
    monkeypatch.setattr(ledger_db, "LEDGER_PATH", path)
    monkeypatch.setattr(ledger_db, "_conn", None)
    conn = ledger_db.get_ledger_db()
    yield conn
    ledger_db.reset_connection_for_tests()


def _seed(conn, uid="s1", model="claude-opus-4-8", tokens_out=1_000_000, workspace="/tmp/p"):
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = conn
    sink.emit(
        UsageEvent(
            event_uid=uid,
            ts=datetime.now(timezone.utc),
            source="test",
            model=model,
            session_uid=uid,
            workspace_path=workspace,
            tokens_in=0,
            tokens_out=tokens_out,
        )
    )


def test_ledger_status_empty(isolated_ledger):
    result = CliRunner().invoke(ledger, ["status"])
    assert result.exit_code == 0
    assert "0 usage events" in result.output


def test_ledger_status_with_data(isolated_ledger):
    _seed(isolated_ledger)
    result = CliRunner().invoke(ledger, ["status"])
    assert result.exit_code == 0
    assert "1 usage events" in result.output
    assert "claude-opus-4-8" in result.output
    assert "Total USD spend" in result.output


def test_ledger_status_labels_guessed_pricing(isolated_ledger, tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    _seed(isolated_ledger, model="provider-model-not-in-table")

    result = CliRunner().invoke(ledger, ["status"])

    assert result.exit_code == 0
    assert "guessed across 1 event" in result.output
    assert "not safe for hard budget decisions" in result.output


def test_ledger_by_workspace(isolated_ledger):
    _seed(isolated_ledger, workspace="/tmp/myproj")
    result = CliRunner().invoke(ledger, ["by-workspace"])
    assert result.exit_code == 0
    assert "myproj" in result.output


def test_ledger_by_workspace_distinguishes_missing_basis(isolated_ledger):
    _seed(isolated_ledger, workspace="/tmp/myproj")

    result = CliRunner().invoke(ledger, ["by-workspace", "--basis", "source_reported"])

    assert result.exit_code == 0
    assert "No USD source_reported postings" in result.output
    assert "1 recorded workspace" in result.output


def test_reconcile_empty(isolated_ledger):
    result = CliRunner().invoke(reconcile, [])
    assert result.exit_code == 0
    assert "No USD pricing_table postings" in result.output


def test_reconcile_no_drift(isolated_ledger):
    _seed(isolated_ledger)
    result = CliRunner().invoke(reconcile, [])
    assert result.exit_code == 0
    assert "No drift" in result.output
    assert "Phase 3" in result.output  # honest deferral message


def test_reconcile_uses_rate_effective_at_event_timestamp(isolated_ledger, monkeypatch):
    _seed(isolated_ledger)
    seen_as_of = []

    def event_effective_cost(*args, as_of=None):
        seen_as_of.append(as_of)
        return 25.0

    monkeypatch.setattr("forecost.commands.reconcile_cmd.calculate_cost", event_effective_cost)

    result = CliRunner().invoke(reconcile, [])

    assert result.exit_code == 0
    assert seen_as_of
    assert seen_as_of[0] == isolated_ledger.execute("SELECT ts FROM usage_events").fetchone()[0]


def test_reconcile_flags_drift(isolated_ledger):
    """When a stored posting's amount disagrees with the current pricing table
    (e.g. a stale pricing_version), reconcile flags it."""
    _seed(isolated_ledger)
    # Corrupt the stored amount so it no longer matches recompute-from-tokens.
    isolated_ledger.execute(
        "UPDATE postings SET amount = amount * 5, pricing_version = 'old-snapshot'"
    )
    isolated_ledger.commit()
    result = CliRunner().invoke(reconcile, [])
    assert result.exit_code == 0
    assert "FLAGS" in result.output
    assert "drift" in result.output


def test_reconcile_flags_nonzero_table_against_zero_source(isolated_ledger):
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = isolated_ledger
    sink.emit(
        UsageEvent(
            event_uid="source-zero",
            ts=datetime.now(timezone.utc),
            source="gateway",
            model="claude-opus-4-8",
            tokens_out=1_000,
            reported_cost=Money(amount=0.0, currency="USD"),
        )
    )

    result = CliRunner().invoke(reconcile, [])

    assert result.exit_code == 0
    assert "1 disagree by >3.0%" in result.output


def test_pricing_audit_rejects_non_usd_until_supported(isolated_ledger):
    result = CliRunner().invoke(pricing_audit, ["--currency", "EUR"])

    assert result.exit_code == 2
    assert "Invalid value for '--currency'" in result.output


def test_burn_no_budgets(isolated_ledger):
    _seed(isolated_ledger)
    result = CliRunner().invoke(burn, [])
    assert result.exit_code == 0
    assert "Trailing" in result.output
    assert "No active budgets" in result.output


def test_burn_with_budget(isolated_ledger):
    _seed(isolated_ledger, tokens_out=100_000)
    now = datetime.now(timezone.utc).isoformat()
    isolated_ledger.execute(
        "INSERT INTO budgets (name, scope, currency, hard_limit, action, created_at) "
        "VALUES ('cap', 'week', 'USD', 100.0, 'warn', ?)",
        (now,),
    )
    isolated_ledger.commit()
    result = CliRunner().invoke(burn, [])
    assert result.exit_code == 0
    assert "budget 'cap'" in result.output


def test_calibration_empty(isolated_ledger):
    result = CliRunner().invoke(calibration, [])
    assert result.exit_code == 0
    assert "No reconciled estimates yet" in result.output


def test_calibration_with_record(isolated_ledger):
    from forecost.estimate.calibration import reconcile_estimates
    from forecost.estimate.engine import record_estimate
    from forecost.estimate.types import EstimateRange
    from forecost.ledger.sink import _get_or_create_session

    est = EstimateRange(
        currency="USD",
        unit="USD",
        p10=0.05,
        p50=0.20,
        p90=1.0,
        n_samples=12,
        method="empirical_quantiles",
        confidence="medium",
        category="bugfix-debug",
    )
    # Real path: an estimate in a session, that session's actuals, then reconcile.
    sess_id = _get_or_create_session(
        isolated_ledger, "s-cal", None, "test", datetime.now(timezone.utc).isoformat()
    )
    record_estimate(isolated_ledger, est, sess_id, None, "s-cal", shadow=True)
    _seed(isolated_ledger, uid="s-cal", tokens_out=4_000)  # ~$0.30, in band, session s-cal
    reconcile_estimates(isolated_ledger)

    result = CliRunner().invoke(calibration, [])
    assert result.exit_code == 0
    assert "Calibration record" in result.output
    assert "shadow-mode" in result.output


def test_ingest_from_tmp_transcripts(isolated_ledger, tmp_path):
    claude_dir = tmp_path / "projects"
    proj = claude_dir / "-tmp-p"
    proj.mkdir(parents=True)
    session = proj / "s.jsonl"
    records = [
        {
            "type": "assistant",
            "requestId": "r1",
            "uuid": "u1",
            "sessionId": "s",
            "cwd": "/tmp/p",
            "timestamp": "2026-07-01T00:00:00Z",
            "message": {
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        },
    ]
    with open(session, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    result = CliRunner().invoke(ingest, ["--claude-dir", str(claude_dir)])
    assert result.exit_code == 0
    assert "Ingested 1 new usage events" in result.output
