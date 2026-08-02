from datetime import date, datetime, timedelta, timezone

from forecost.adapters.base import Money, UsageEvent, content_free_identifier
from forecost.ledger import queries as q
from forecost.ledger.sink import SyncLedgerSink
from forecost.policy.engine import evaluate
from forecost.policy.rules import parse_policy_toml
from forecost.pricing import calculate_cost, get_pricing_period


def _emit(
    conn,
    *,
    uid: str,
    session_uid: str,
    model: str,
    tokens_in: int = 1_000_000,
    tokens_out: int = 0,
    ts: datetime | None = None,
    reported_cost: Money | None = None,
) -> int:
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = conn
    sink.emit(
        UsageEvent(
            event_uid=uid,
            ts=ts or datetime.now(timezone.utc),
            source="test",
            model=model,
            session_uid=session_uid,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            reported_cost=reported_cost,
        )
    )
    normalized_session = content_free_identifier("session", session_uid)
    return conn.execute(
        "SELECT id FROM sessions WHERE session_uid = ?", (normalized_session,)
    ).fetchone()["id"]


def _deny_policy(*, soft: float | None = None, hard: float = 2.0):
    soft_line = f"soft_limit={soft}\n" if soft is not None else ""
    return parse_policy_toml(
        '[[policy.rules]]\nid="cap"\nscope="session"\ncurrency="USD"\n'
        f'{soft_line}hard_limit={hard}\naction="deny"\n'
    )


def test_sonnet_5_intro_rate_applies_through_august_31_utc():
    at_boundary = datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc)

    assert calculate_cost("claude-sonnet-5", 1_000_000, 1_000_000, as_of=at_boundary) == 12.0
    assert get_pricing_period("claude-sonnet-5", at_boundary) == (
        "sonnet5-intro-through-2026-08-31"
    )


def test_sonnet_5_standard_rate_starts_september_1_utc():
    after_boundary = datetime(2026, 9, 1, tzinfo=timezone.utc)

    assert calculate_cost("claude-sonnet-5", 1_000_000, 1_000_000, as_of=after_boundary) == 18.0
    assert get_pricing_period("claude-sonnet-5", after_boundary) == (
        "sonnet5-standard-from-2026-09-01"
    )


def test_sonnet_5_effective_date_normalizes_aware_timestamp_to_utc():
    central = timezone(-timedelta(hours=5))
    local_august = datetime(2026, 8, 31, 20, 0, tzinfo=central)

    assert calculate_cost("claude-sonnet-5", 1_000_000, 1_000_000, as_of=local_august) == 18.0


def test_sonnet_5_family_suffix_uses_effective_dated_rate():
    assert (
        calculate_cost(
            "claude-sonnet-5-preview",
            1_000_000,
            1_000_000,
            as_of=date(2026, 8, 31),
        )
        == 12.0
    )
    assert get_pricing_period("claude-sonnet-5-preview", date(2026, 8, 31)) == (
        "sonnet5-intro-through-2026-08-31"
    )


def test_sonnet_5_effective_date_accepts_naive_datetime_and_date():
    naive_event_time = datetime(2026, 8, 31, 23, 59)  # noqa: DTZ001 - deliberately naive input
    assert get_pricing_period("claude-sonnet-5", naive_event_time) == (
        "sonnet5-intro-through-2026-08-31"
    )
    assert get_pricing_period("claude-sonnet-5", date(2026, 9, 1)) == (
        "sonnet5-standard-from-2026-09-01"
    )


def test_sonnet_5_effective_date_accepts_iso_strings():
    assert get_pricing_period("claude-sonnet-5", "2026-09-01T00:30:00+01:00") == (
        "sonnet5-intro-through-2026-08-31"
    )
    assert get_pricing_period("claude-sonnet-5", "2026-09-01T00:00:00") == (
        "sonnet5-standard-from-2026-09-01"
    )


def test_sonnet_5_default_effective_date_uses_current_utc_date(monkeypatch):
    import forecost.pricing as pricing

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 31, 23, 59, tzinfo=tz)

    monkeypatch.setattr(pricing, "datetime", FixedDatetime)

    assert get_pricing_period("claude-sonnet-5") == "sonnet5-intro-through-2026-08-31"


def test_sonnet_5_date_only_string_fallback(monkeypatch):
    import forecost.pricing as pricing

    class DateOnlyFallback(datetime):
        @classmethod
        def fromisoformat(cls, value):
            raise ValueError(value)

    monkeypatch.setattr(pricing, "datetime", DateOnlyFallback)

    assert get_pricing_period("claude-sonnet-5", "2026-09-01") == (
        "sonnet5-standard-from-2026-09-01"
    )


def test_sink_prices_sonnet_5_by_event_timestamp_and_records_period(ledger_conn):
    _emit(
        ledger_conn,
        uid="sonnet-intro",
        session_uid="sonnet-session",
        model="claude-sonnet-5",
        ts=datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc),
    )
    _emit(
        ledger_conn,
        uid="sonnet-standard",
        session_uid="sonnet-session",
        model="claude-sonnet-5",
        ts=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )

    rows = {
        row["event_uid"]: row
        for row in ledger_conn.execute(
            """
            SELECT e.event_uid, p.amount, p.pricing_version
            FROM usage_events e JOIN postings p ON p.event_id = e.id
            """
        )
    }
    intro = rows[content_free_identifier("event", "sonnet-intro")]
    standard = rows[content_free_identifier("event", "sonnet-standard")]
    assert intro["amount"] == 2.0
    assert standard["amount"] == 3.0
    assert intro["pricing_version"].endswith("/sonnet5-intro-through-2026-08-31")
    assert standard["pricing_version"].endswith("/sonnet5-standard-from-2026-09-01")


def test_query_preserves_unpriced_amount_separately(ledger_conn):
    _emit(
        ledger_conn,
        uid="unknown-only",
        session_uid="unknown-session",
        model="brand-new-model",
    )

    spend = q.scope_spend(ledger_conn, "USD", "1970-01-01T00:00:00+00:00")
    assert spend.total == 5.0
    assert spend.confident_total == 0.0
    assert spend.unpriced_total == 5.0
    assert spend.n_confident_events == 0
    assert spend.n_unpriced_events == 1
    assert spend.fully_priced is False


def test_missing_pricing_provenance_is_not_treated_as_confident(ledger_conn):
    _emit(
        ledger_conn,
        uid="missing-version",
        session_uid="missing-version-session",
        model="claude-opus-4-8",
    )
    ledger_conn.execute("UPDATE postings SET pricing_version = NULL")
    ledger_conn.commit()

    spend = q.scope_spend(ledger_conn, "USD", "1970-01-01T00:00:00+00:00")

    assert spend.confident_total == 0.0
    assert spend.unpriced_total == 5.0


def test_unpriced_estimate_cannot_trigger_hard_deny(ledger_conn):
    session_id = _emit(
        ledger_conn,
        uid="guess",
        session_uid="guess-session",
        model="brand-new-model",
    )

    decision = evaluate(ledger_conn, _deny_policy(), session_id=session_id)

    assert decision.action == "warn"
    assert decision.measured == 5.0
    assert "unpriced models" in decision.reason
    assert "hard action suppressed" in decision.reason


def test_source_reported_amount_for_unknown_model_can_deny(ledger_conn):
    session_id = _emit(
        ledger_conn,
        uid="reported",
        session_uid="reported-session",
        model="brand-new-model",
        reported_cost=Money(amount=3.0, currency="USD"),
    )

    spend = q.session_spend_breakdown(ledger_conn, session_id)
    decision = evaluate(ledger_conn, _deny_policy(), session_id=session_id)

    assert spend.total == 3.0
    assert spend.confident_total == 3.0
    assert spend.n_unpriced_events == 0
    assert decision.action == "deny"
    assert decision.measured == 3.0


def test_confirmed_amount_can_deny_while_guess_is_excluded(ledger_conn):
    session_id = _emit(
        ledger_conn,
        uid="known",
        session_uid="mixed-session",
        model="claude-opus-4-8",
        tokens_in=600_000,
    )
    _emit(
        ledger_conn,
        uid="unknown",
        session_uid="mixed-session",
        model="brand-new-model",
    )

    decision = evaluate(ledger_conn, _deny_policy(), session_id=session_id)

    assert decision.action == "deny"
    assert decision.measured == 3.0
    assert "excluded USD 5.00" in decision.reason


def test_soft_warning_labels_unpriced_amount(ledger_conn):
    session_id = _emit(
        ledger_conn,
        uid="soft-guess",
        session_uid="soft-session",
        model="brand-new-model",
    )

    decision = evaluate(ledger_conn, _deny_policy(soft=4.0, hard=10.0), session_id=session_id)

    assert decision.action == "warn"
    assert "includes 5.00 from unpriced models" in decision.reason
