from datetime import datetime, timezone

from click.testing import CliRunner

from forecost.adapters.base import UsageEvent, content_free_identifier
from forecost.commands.pricing_audit_cmd import pricing_audit
from forecost.ledger.sink import SyncLedgerSink


def _emit(conn, *, uid: str, model: str, tokens_in: int = 1_000_000) -> None:
    sink = SyncLedgerSink(ledger_path=None)
    sink._conn = conn
    sink.emit(
        UsageEvent(
            event_uid=uid,
            ts=datetime(2026, 8, 1, tzinfo=timezone.utc),
            source="test",
            model=model,
            session_uid=uid,
            tokens_in=tokens_in,
            tokens_out=0,
        )
    )


def test_pricing_audit_reports_empty_or_fully_priced_ledger(ledger_conn, monkeypatch):
    import forecost.commands.pricing_audit_cmd as audit_module

    _emit(ledger_conn, uid="known", model="claude-opus-4-8")
    monkeypatch.setattr(audit_module, "get_ledger_db", lambda: ledger_conn)

    result = CliRunner().invoke(pricing_audit)

    assert result.exit_code == 0
    assert "Pricing table: bundled-2026-08" in result.output
    assert "DEFAULT_COST guess of $5.00/$15.00 per MTok" in result.output
    assert "No unpriced models in the ledger" in result.output


def test_pricing_audit_ranks_and_totals_only_guessed_models(ledger_conn, monkeypatch):
    import forecost.commands.pricing_audit_cmd as audit_module

    _emit(ledger_conn, uid="small-guess", model="unknown-small", tokens_in=1_000_000)
    _emit(ledger_conn, uid="large-guess-1", model="unknown-large", tokens_in=2_000_000)
    _emit(ledger_conn, uid="large-guess-2", model="unknown-large", tokens_in=1_000_000)
    _emit(ledger_conn, uid="known", model="claude-opus-4-8", tokens_in=9_000_000)
    monkeypatch.setattr(audit_module, "get_ledger_db", lambda: ledger_conn)

    result = CliRunner().invoke(pricing_audit, ["--currency", "usd"])

    assert result.exit_code == 0
    assert (
        "2 model(s) priced by GUESS (USD 20.00 of spend is not from a real rate)" in result.output
    )
    large_model = content_free_identifier("model", "unknown-large")
    small_model = content_free_identifier("model", "unknown-small")
    assert large_model in result.output
    assert "n=2" in result.output
    assert "USD 15.00 (guessed)" in result.output
    assert small_model in result.output
    assert "n=1" in result.output
    assert "USD 5.00 (guessed)" in result.output
    assert result.output.index(large_model) < result.output.index(small_model)
    assert "claude-opus-4-8" not in result.output
    assert "Budget rules should not hard-deny on guessed prices" in result.output
