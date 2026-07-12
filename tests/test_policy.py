from datetime import datetime, timezone

import pytest

from forecost.adapters.base import UsageEvent
from forecost.ledger.sink import SyncLedgerSink, _get_or_create_session
from forecost.policy.engine import evaluate
from forecost.policy.rules import parse_policy_toml


def _spend(conn, session_uid, usd, event_uid="e1"):
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = conn
    sink.emit(
        UsageEvent(
            event_uid=event_uid,
            ts=datetime.now(timezone.utc),
            source="test",
            model="claude-opus-4-8",
            session_uid=session_uid,
            tokens_in=int(usd / 15 * 1_000_000),
            tokens_out=0,
        )
    )


def test_parse_policy_toml_basic():
    config = parse_policy_toml(
        '[[policy.rules]]\nid="cap"\nscope="session"\ncurrency="USD"\n'
        'soft_limit=5.0\nhard_limit=10.0\naction="deny"\n'
    )
    assert len(config.rules) == 1
    r = config.rules[0]
    assert r.rule_id == "cap"
    assert r.hard_limit == 10.0
    assert r.action == "deny"


def test_parse_policy_toml_rejects_fail_closed_outside_ci():
    """BASEMENT.md law L4: on_internal_error='deny' is illegal outside CI mode."""
    with pytest.raises(ValueError, match="fail-open"):
        parse_policy_toml('[policy]\non_internal_error = "deny"\n')


def test_parse_policy_toml_allows_fail_closed_in_ci_mode():
    config = parse_policy_toml('[policy]\nmode = "ci"\non_internal_error = "deny"\n')
    assert config.on_internal_error == "deny"


def test_parse_policy_toml_rejects_invalid_action():
    with pytest.raises(ValueError, match="invalid policy action"):
        parse_policy_toml('[[policy.rules]]\nid="x"\naction="explode"\n')


def test_evaluate_allows_within_soft_limit(ledger_conn):
    config = parse_policy_toml(
        '[[policy.rules]]\nid="cap"\nscope="session"\ncurrency="USD"\n'
        'soft_limit=5.0\nhard_limit=10.0\naction="deny"\n'
    )
    sess_id = _get_or_create_session(ledger_conn, "s1", None, "test", "2026-01-01")
    _spend(ledger_conn, "s1", 2.0)
    d = evaluate(ledger_conn, config, session_id=sess_id)
    assert d.action == "allow"
    assert d.rule_id == "cap"


def test_evaluate_warns_above_soft_limit(ledger_conn):
    config = parse_policy_toml(
        '[[policy.rules]]\nid="cap"\nscope="session"\ncurrency="USD"\n'
        'soft_limit=1.0\nhard_limit=10.0\naction="deny"\n'
    )
    sess_id = _get_or_create_session(ledger_conn, "s2", None, "test", "2026-01-01")
    _spend(ledger_conn, "s2", 2.0)
    d = evaluate(ledger_conn, config, session_id=sess_id)
    assert d.action == "warn"


def test_evaluate_denies_above_hard_limit(ledger_conn):
    config = parse_policy_toml(
        '[[policy.rules]]\nid="cap"\nscope="session"\ncurrency="USD"\n'
        'soft_limit=1.0\nhard_limit=2.0\naction="deny"\n'
    )
    sess_id = _get_or_create_session(ledger_conn, "s3", None, "test", "2026-01-01")
    _spend(ledger_conn, "s3", 5.0)
    d = evaluate(ledger_conn, config, session_id=sess_id)
    assert d.action == "deny"
    assert d.rule_id == "cap"


def test_evaluate_fails_open_on_internal_error(ledger_conn):
    class Broken:
        rules = None  # not iterable -> forces an internal exception

    d = evaluate(ledger_conn, Broken())  # type: ignore[arg-type]  # intentionally malformed
    assert d.action == "allow"
    assert "fail-open" in d.reason


def test_evaluate_strictest_rule_wins_across_multiple_rules(ledger_conn):
    config = parse_policy_toml(
        '[[policy.rules]]\nid="loose"\nscope="session"\ncurrency="USD"\n'
        'soft_limit=100.0\nhard_limit=200.0\naction="warn"\n'
        '[[policy.rules]]\nid="strict"\nscope="session"\ncurrency="USD"\n'
        'soft_limit=1.0\nhard_limit=2.0\naction="deny"\n'
    )
    sess_id = _get_or_create_session(ledger_conn, "s4", None, "test", "2026-01-01")
    _spend(ledger_conn, "s4", 5.0)
    d = evaluate(ledger_conn, config, session_id=sess_id)
    assert d.action == "deny"
    assert d.rule_id == "strict"
