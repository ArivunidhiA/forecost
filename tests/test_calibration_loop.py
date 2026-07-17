"""Tests for the estimate → actual reconciliation loop and burn trajectory.

The estimate↔actual association is by session + time window (not run_id), so
these tests drive the real production path: a session is created, an estimate is
recorded against it, that session's events are ingested, then reconcile runs.
"""

from datetime import datetime, timedelta, timezone

from forecost.adapters.base import UsageEvent
from forecost.estimate.calibration import calibration_by_category, reconcile_estimates
from forecost.estimate.engine import record_estimate
from forecost.estimate.trajectory import burn_report
from forecost.estimate.types import EstimateRange
from forecost.ledger import queries as q
from forecost.ledger.sink import SyncLedgerSink, _get_or_create_session


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


def _session(conn, uid):
    return _get_or_create_session(conn, uid, None, "test", datetime.now(timezone.utc).isoformat())


def _spend_in_session(conn, session_uid, usd, uid, ts=None):
    """Emit a claude-opus-4-8 event (output $25/Mtok) worth ~`usd` into a session."""
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = conn
    sink.emit(
        UsageEvent(
            event_uid=uid,
            ts=ts or datetime.now(timezone.utc),
            source="test",
            model="claude-opus-4-8",
            session_uid=session_uid,
            tokens_in=0,
            tokens_out=int(usd / 25 * 1_000_000),  # opus-4-8 output rate $25/MTok
        )
    )


def _record_run(conn, session_uid, est, usd, uid):
    """One full turn: record an estimate in a session, then ingest its actuals."""
    sess_id = _session(conn, session_uid)
    record_estimate(conn, est, sess_id, None, session_uid, shadow=True)
    _spend_in_session(conn, session_uid, usd, uid)


def test_reconcile_estimates_scores_within_band(ledger_conn):
    _record_run(ledger_conn, "s-in-band", _estimate(), 0.30, "e1")  # inside [0.05, 1.00]

    written = reconcile_estimates(ledger_conn)
    assert written == 1

    row = ledger_conn.execute("SELECT * FROM reconciliations").fetchone()
    assert row["within_band"] == 1
    assert row["actual_amount"] > 0


def test_reconcile_estimates_scores_band_miss(ledger_conn):
    _record_run(ledger_conn, "s-miss", _estimate(p90=0.10), 5.0, "e2")  # above p90=0.10

    reconcile_estimates(ledger_conn)
    row = ledger_conn.execute("SELECT * FROM reconciliations").fetchone()
    assert row["within_band"] == 0


def test_reconcile_estimates_is_idempotent(ledger_conn):
    _record_run(ledger_conn, "s-x", _estimate(), 0.30, "e3")
    assert reconcile_estimates(ledger_conn) == 1
    assert reconcile_estimates(ledger_conn) == 0  # already scored, never re-scored


def test_reconcile_cold_start_records_actual_but_no_band(ledger_conn):
    """A cold-start estimate still gets its actual recorded (so it can train the
    estimator), but a 0/0/0 band is not scored — within_band stays NULL and it is
    excluded from the published coverage record."""
    _record_run(
        ledger_conn,
        "s-cold",
        _estimate(p10=0, p50=0, p90=0, method="cold_start_prior"),
        0.30,
        "e4",
    )
    assert reconcile_estimates(ledger_conn) == 1  # actual recorded for training
    row = ledger_conn.execute("SELECT * FROM reconciliations").fetchone()
    assert row["within_band"] is None
    assert row["actual_amount"] > 0
    # Excluded from the published record.
    assert q.calibration_summary(ledger_conn, currency="USD")["n"] == 0


def test_reconcile_estimates_waits_for_actuals(ledger_conn):
    sess_id = _session(ledger_conn, "s-pending")
    record_estimate(ledger_conn, _estimate(), sess_id, None, "s-pending", shadow=True)
    # no spend ingested yet
    assert reconcile_estimates(ledger_conn) == 0
    # actuals arrive later -> scored on the next pass
    _spend_in_session(ledger_conn, "s-pending", 0.30, "e5")
    assert reconcile_estimates(ledger_conn) == 1


def test_reconcile_windows_two_turns_in_one_session(ledger_conn):
    """Two estimates in the same session are each scored against only their own
    turn's events (the window between consecutive estimates), not the sum."""
    sess_id = _session(ledger_conn, "s-two")
    t0 = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=5)
    # Turn 1 estimate + its event, then turn 2 estimate + its event.
    record_estimate(
        ledger_conn, _estimate(), sess_id, None, "s-two", shadow=True
    )  # created_at ~ now (earliest)
    ledger_conn.execute(
        "UPDATE estimates SET created_at = ? WHERE run_id = 's-two' AND created_at = "
        "(SELECT MAX(created_at) FROM estimates WHERE run_id = 's-two')",
        (t0.isoformat(),),
    )
    _spend_in_session(ledger_conn, "s-two", 0.30, "ev1", ts=t0 + timedelta(minutes=1))
    record_estimate(ledger_conn, _estimate(p90=0.10), sess_id, None, "s-two", shadow=True)
    ledger_conn.execute(
        "UPDATE estimates SET created_at = ? WHERE run_id = 's-two' AND created_at = "
        "(SELECT MAX(created_at) FROM estimates WHERE run_id = 's-two')",
        (t1.isoformat(),),
    )
    _spend_in_session(ledger_conn, "s-two", 5.0, "ev2", ts=t1 + timedelta(minutes=1))
    ledger_conn.commit()

    assert reconcile_estimates(ledger_conn) == 2
    rows = ledger_conn.execute(
        "SELECT within_band, actual_amount FROM reconciliations "
        "JOIN estimates ON estimates.id = reconciliations.estimate_id ORDER BY estimates.created_at"
    ).fetchall()
    # Turn 1 saw only its 0.30 event (in band); turn 2 saw only its 5.0 event (miss).
    assert rows[0]["within_band"] == 1
    assert abs(rows[0]["actual_amount"] - 0.30) < 0.01
    assert rows[1]["within_band"] == 0
    assert abs(rows[1]["actual_amount"] - 5.0) < 0.01


def test_calibration_summary_and_by_category(ledger_conn):
    _record_run(ledger_conn, "s-r1", _estimate(), 0.30, "e6")  # in band
    _record_run(ledger_conn, "s-r2", _estimate(p90=0.10), 5.0, "e7")  # miss
    reconcile_estimates(ledger_conn)

    summary = q.calibration_summary(ledger_conn, currency="USD")
    assert summary["n"] == 2
    assert summary["coverage"] == 0.5

    by_cat = calibration_by_category(ledger_conn, currency="USD")
    assert by_cat[0]["category"] == "bugfix-debug"
    assert by_cat[0]["n"] == 2


def test_burn_report_without_budgets(ledger_conn):
    _spend_in_session(ledger_conn, "s-burn", 12.0, "e8")
    reports = burn_report(ledger_conn, window_hours=24.0)
    assert len(reports) == 1
    assert reports[0].spent_in_window > 0
    assert reports[0].hourly_rate == reports[0].spent_in_window / 24.0
    assert reports[0].budget_name is None


def test_burn_report_projects_time_to_limit(ledger_conn):
    _spend_in_session(ledger_conn, "s-burn2", 12.0, "e9")
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
    old_ts = datetime.now(timezone.utc) - timedelta(days=10)
    _spend_in_session(ledger_conn, "s-old", 75.0, "old", ts=old_ts)
    reports = burn_report(ledger_conn, window_hours=24.0)
    assert reports[0].spent_in_window == 0
