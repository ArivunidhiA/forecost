from datetime import datetime, timezone

from forecost.adapters.base import UsageEvent
from forecost.estimate.calibration import reconcile_estimates
from forecost.estimate.engine import estimate_cost, record_estimate
from forecost.estimate.flags import plan_missing_test_step, scan_prompt
from forecost.estimate.guard import check_error_streak, check_spend_since_progress
from forecost.estimate.taxonomy import classify
from forecost.estimate.types import TaskContext
from forecost.ledger.sink import SyncLedgerSink, _get_or_create_session


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


def test_estimate_warms_up_from_reconciled_history(ledger_conn):
    """The estimator trains from reconciled actuals, so warm-up goes through the
    real loop: record an estimate in a session, ingest that session's actuals,
    reconcile, repeat. After enough turns the category has empirical history."""
    task = TaskContext(prompt_text="fix a bug", cwd="/tmp/p")
    category = "bugfix-debug"
    cold = estimate_cost(ledger_conn, task, category)
    assert cold.method == "cold_start_prior"

    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = ledger_conn
    for i in range(5):
        session_uid = f"sess-{i}"  # one turn per session -> open-ended window each
        sess_id = _get_or_create_session(
            ledger_conn, session_uid, None, "test", datetime.now(timezone.utc).isoformat()
        )
        record_estimate(ledger_conn, cold, sess_id, None, session_uid, shadow=True)
        sink.emit(
            UsageEvent(
                event_uid=f"e{i}",
                ts=datetime.now(timezone.utc),
                source="test",
                model="claude-sonnet-4-20250514",
                session_uid=session_uid,
                tokens_in=100_000,
                tokens_out=10_000,
            )
        )
    reconcile_estimates(ledger_conn)

    warm = estimate_cost(ledger_conn, task, category)
    assert warm.n_samples == 5
    assert warm.method == "empirical_quantiles"
    assert warm.p10 <= warm.p50 <= warm.p90
    # Each turn cost $0.45 (100k in @ $3/Mtok + 10k out @ $15/Mtok). The estimate
    # must sit at the observed cost, NOT collapse toward zero as the old buggy
    # `w * q` shrinkage did (which would have produced p50 ~ $0.13 here).
    assert 0.40 <= warm.p50 <= 0.50


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
    # The tail rule requires the recent window to END on an error (the backtested
    # conjunct) — two early errors with a clean tail must NOT flag.
    assert check_error_streak(0, 2, tail_has_error=False) is None
    assert check_error_streak(0, 2, tail_has_error=True) is not None


def test_guard_evidence_is_a_measured_fact_not_a_prediction():
    ev = check_error_streak(consecutive_errors=4, total_errors_in_tail=0)
    assert ev is not None
    assert "4 consecutive" in ev.fact
    assert "fail" not in ev.fact.lower()
    assert "likely" not in ev.fact.lower()


def test_guard_spend_since_progress():
    assert check_spend_since_progress(0.5, threshold_usd=2.0) is None
    ev = check_spend_since_progress(3.0, threshold_usd=2.0)
    assert ev is not None
    assert "3.00" in ev.fact


def _err_result(is_error):
    return {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "is_error": is_error, "content": "x"}]},
    }


def test_scan_transcript_errors_is_content_free_and_fires_on_streak(tmp_path):
    import json

    from forecost.estimate.guard import scan_transcript_errors

    t = tmp_path / "sess.jsonl"
    # 3 consecutive tool errors -> the consec rule fires.
    with open(t, "w", encoding="utf-8") as f:
        for _ in range(3):
            f.write(json.dumps(_err_result(True)) + "\n")
    ev = scan_transcript_errors(str(t))
    assert ev is not None
    assert ev.rule_id == "consec_tool_errors"

    # Two early errors then a clean recent window (>=5 clean results) must NOT
    # flag — this is exactly the drift the tail_has_error conjunct fixes (the old
    # rule fired on total>=2 regardless of the tail).
    t2 = tmp_path / "clean.jsonl"
    with open(t2, "w", encoding="utf-8") as f:
        f.write(json.dumps(_err_result(True)) + "\n")
        f.write(json.dumps(_err_result(True)) + "\n")
        for _ in range(5):
            f.write(json.dumps(_err_result(False)) + "\n")  # window ends clean
    assert scan_transcript_errors(str(t2)) is None
    assert scan_transcript_errors("/does/not/exist.jsonl") is None


def test_scan_transcript_uses_current_streak_and_final_tail_result(tmp_path):
    import json

    from forecost.estimate.guard import scan_transcript_errors

    transcript = tmp_path / "recovered.jsonl"
    with open(transcript, "w", encoding="utf-8") as stream:
        # This historical streak is still inside the five-result window, but
        # clean progress followed it. Neither rule describes the current tail.
        for is_error in (True, True, True, False, False):
            stream.write(json.dumps(_err_result(is_error)) + "\n")

    assert scan_transcript_errors(str(transcript)) is None


def test_scan_transcript_reads_a_bounded_suffix_of_large_history(tmp_path):
    import json

    from forecost.estimate.guard import scan_transcript_errors

    transcript = tmp_path / "large.jsonl"
    with transcript.open("wb") as stream:
        stream.write(b"x" * (5 * 1024 * 1024) + b"\n")
        for _ in range(3):
            stream.write(json.dumps(_err_result(True)).encode() + b"\n")

    evidence = scan_transcript_errors(str(transcript))
    assert evidence is not None
    assert evidence.rule_id == "consec_tool_errors"


def test_record_guard_flag_writes_shadow_row(ledger_conn):
    from forecost.estimate.guard import GuardEvidence, record_guard_flag

    ev = GuardEvidence("consec_tool_errors", "3 consecutive")
    record_guard_flag(ledger_conn, None, "run-1", ev, shadow=True)
    row = ledger_conn.execute("SELECT rule_id, evidence, shadow FROM guard_flags").fetchone()
    assert row["rule_id"] == "consec_tool_errors"
    assert row["evidence"] == "3 consecutive"
    assert row["shadow"] == 1
