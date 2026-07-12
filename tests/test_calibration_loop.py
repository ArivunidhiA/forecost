"""Tests for the estimate → actual reconciliation loop and burn trajectory."""

from datetime import datetime, timedelta, timezone

from forecost.adapters.base import UsageEvent
from forecost.estimate.calibration import calibration_by_category, reconcile_estimates
from forecost.estimate.engine import record_estimate
from forecost.estimate.trajectory import burn_report
from forecost.estimate.types import EstimateRange
from forecost.ledger import queries as q
from forecost.ledger.sink import SyncLedgerSink


def _estimate(category="bugfix-debug", p10=0.05, p50=0.20, p90=1.00, method="empirical_quantiles"):
    return EstimateRange(
        currency="USD",
        unit="USD",
        p10=p10,
        p50=p50,
        p90=p90,
        n_samples=12,
        method=method,
        confidence="medium",
        category=category,
    )


def _spend(conn, run_id, usd, uid):
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = conn
    # claude-opus-4-8 output rate is $75/Mtok -> tokens_out for target usd
    sink.emit(
        UsageEvent(
            event_uid=uid,
            ts=datetime.now(timezone.utc),
            source="test",
            model="claude-opus-4-8",
            run_id=run_id,
            tokens_in=0,
            tokens_out=int(usd / 75 * 1_000_000),
        )
    )


def test_reconcile_estimates_scores_within_band(ledger_conn):
    record_estimate(ledger_conn, _estimate(), None, None, "run-in-band", shadow=True)
    _spend(ledger_conn, "run-in-band", 0.30, "e1")  # inside [0.05, 1.00]

    written = reconcile_estimates(ledger_conn)
    assert written == 1

    row = ledger_conn.execute("SELECT * FROM reconciliations").fetchone()
    assert row["within_band"] == 1
    assert row["actual_amount"] > 0


def test_reconcile_estimates_scores_band_miss(ledger_conn):
    record_estimate(ledger_conn, _estimate(p90=0.10), None, None, "run-miss", shadow=True)
    _spend(ledger_conn, "run-miss", 5.0, "e2")  # way above p90=0.10

    reconcile_estimates(ledger_conn)
    row = ledger_conn.execute("SELECT * FROM reconciliations").fetchone()
    assert row["within_band"] == 0


def test_reconcile_estimates_is_idempotent(ledger_conn):
    record_estimate(ledger_conn, _estimate(), None, None, "run-x", shadow=True)
    _spend(ledger_conn, "run-x", 0.30, "e3")
    assert reconcile_estimates(ledger_conn) == 1
    assert reconcile_estimates(ledger_conn) == 0  # already scored, never re-scored


def test_reconcile_estimates_skips_cold_start(ledger_conn):
    record_estimate(
        ledger_conn,
        _estimate(p10=0, p50=0, p90=0, method="cold_start_prior"),
        None,
        None,
        "run-cold",
        shadow=True,
    )
    _spend(ledger_conn, "run-cold", 0.30, "e4")
    assert reconcile_estimates(ledger_conn) == 0  # a 0/0/0 band is not a claim


def test_reconcile_estimates_waits_for_actuals(ledger_conn):
    record_estimate(ledger_conn, _estimate(), None, None, "run-pending", shadow=True)
    # no spend ingested yet
    assert reconcile_estimates(ledger_conn) == 0
    # actuals arrive later -> scored on the next pass
    _spend(ledger_conn, "run-pending", 0.30, "e5")
    assert reconcile_estimates(ledger_conn) == 1


def test_calibration_summary_and_by_category(ledger_conn):
    record_estimate(ledger_conn, _estimate(), None, None, "r1", shadow=True)
    record_estimate(ledger_conn, _estimate(p90=0.10), None, None, "r2", shadow=True)
    _spend(ledger_conn, "r1", 0.30, "e6")  # in band
    _spend(ledger_conn, "r2", 5.0, "e7")  # miss
    reconcile_estimates(ledger_conn)

    summary = q.calibration_summary(ledger_conn, currency="USD")
    assert summary["n"] == 2
    assert summary["coverage"] == 0.5

    by_cat = calibration_by_category(ledger_conn, currency="USD")
    assert by_cat[0]["category"] == "bugfix-debug"
    assert by_cat[0]["n"] == 2


def test_burn_report_without_budgets(ledger_conn):
    _spend(ledger_conn, "r", 12.0, "e8")
    reports = burn_report(ledger_conn, window_hours=24.0)
    assert len(reports) == 1
    assert reports[0].spent_in_window > 0
    assert reports[0].hourly_rate == reports[0].spent_in_window / 24.0
    assert reports[0].budget_name is None


def test_burn_report_projects_time_to_limit(ledger_conn):
    _spend(ledger_conn, "r", 12.0, "e9")
    now = datetime.now(timezone.utc).isoformat()
    ledger_conn.execute(
        "INSERT INTO budgets (name, scope, currency, hard_limit, action, created_at) "
        "VALUES ('weekly-cap', 'week', 'USD', 100.0, 'warn', ?)",
        (now,),
    )
    ledger_conn.commit()

    reports = burn_report(ledger_conn, window_hours=24.0)
    r = reports[0]
    assert r.budget_name == "weekly-cap"
    assert r.spent_toward_budget is not None
    assert r.spent_toward_budget > 0
    assert r.hours_to_limit is not None
    assert r.hours_to_limit > 0


def test_burn_report_ignores_old_spend(ledger_conn):
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    old_ts = datetime.now(timezone.utc) - timedelta(days=10)
    sink.emit(
        UsageEvent(
            event_uid="old",
            ts=old_ts,
            source="test",
            model="claude-opus-4-8",
            tokens_in=0,
            tokens_out=1_000_000,
        )
    )
    reports = burn_report(ledger_conn, window_hours=24.0)
    assert reports[0].spent_in_window == 0
