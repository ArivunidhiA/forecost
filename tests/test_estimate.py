from datetime import datetime, timezone

from forecost.adapters.base import UsageEvent
from forecost.estimate.engine import estimate_cost, record_estimate
from forecost.estimate.flags import plan_missing_test_step, scan_prompt
from forecost.estimate.guard import check_error_streak, check_spend_since_progress
from forecost.estimate.taxonomy import classify
from forecost.estimate.types import TaskContext
from forecost.ledger.sink import SyncLedgerSink


def test_taxonomy_classifies_common_prompts():
    assert classify("fix the login bug") == "bugfix-debug"
    assert classify("write tests for the parser") == "test-work"
    assert classify("spawn parallel subagents to review") == "fanout-batch"
    assert classify("update the readme") == "docs-writing"
    assert classify("thanks") == "continuation-misc"


def test_estimate_cold_start_has_no_point_and_zero_confidence(ledger_conn):
    task = TaskContext(prompt_text="do something novel", cwd="/tmp/p")
    est = estimate_cost(ledger_conn, task, "novel-category-never-seen")
    assert est.method == "cold_start_prior"
    assert est.confidence == "low"
    assert "cold_start" in est.caveats
    assert not hasattr(est, "point")  # EstimateRange has no point field, by design


def test_estimate_warms_up_from_recorded_history(ledger_conn):
    task = TaskContext(prompt_text="fix a bug", cwd="/tmp/p")
    category = "bugfix-debug"
    cold = estimate_cost(ledger_conn, task, category)

    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    for i in range(5):
        run_id = f"run-{i}"
        record_estimate(ledger_conn, cold, None, None, run_id, shadow=True)
        sink.emit(
            UsageEvent(
                event_uid=f"e{i}",
                ts=datetime.now(timezone.utc),
                source="test",
                model="claude-sonnet-4-20250514",
                run_id=run_id,
                tokens_in=100_000,
                tokens_out=10_000,
            )
        )

    warm = estimate_cost(ledger_conn, task, category)
    assert warm.n_samples == 5
    assert warm.method == "empirical_quantiles"
    assert warm.p10 <= warm.p50 <= warm.p90


def test_scan_prompt_detects_scope_maximizer_and_sensitive_path():
    flags = scan_prompt("refactor the entire auth/session.py module")
    ids = {f.flag_id for f in flags}
    assert "scope_maximizer" in ids
    assert "sensitive_path_mention" in ids


def test_scan_prompt_quiet_on_ordinary_prompt():
    flags = scan_prompt("fix the typo on line 42")
    assert flags == []


def test_static_flags_never_predict_only_state_facts():
    """L6: flags must describe the text, never claim an outcome."""
    flags = scan_prompt("refactor the entire codebase")
    for f in flags:
        assert "will" not in f.fact.lower()
        assert "probably" not in f.fact.lower()
        assert "likely" not in f.fact.lower()


def test_plan_missing_test_step():
    assert plan_missing_test_step("1. Edit file\n2. Commit") is True
    assert plan_missing_test_step("1. Edit file\n2. Run tests\n3. Commit") is False


def test_guard_error_streak_thresholds():
    assert check_error_streak(consecutive_errors=1, total_errors_in_tail=0) is None
    assert check_error_streak(consecutive_errors=3, total_errors_in_tail=0) is not None
    assert check_error_streak(consecutive_errors=0, total_errors_in_tail=2) is not None


def test_guard_evidence_is_a_measured_fact_not_a_prediction():
    ev = check_error_streak(consecutive_errors=4, total_errors_in_tail=0)
    assert "4 consecutive" in ev.fact
    assert "fail" not in ev.fact.lower()
    assert "likely" not in ev.fact.lower()


def test_guard_spend_since_progress():
    assert check_spend_since_progress(0.5, threshold_usd=2.0) is None
    ev = check_spend_since_progress(3.0, threshold_usd=2.0)
    assert ev is not None
    assert "3.00" in ev.fact
