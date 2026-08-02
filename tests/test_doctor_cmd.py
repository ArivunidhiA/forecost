from datetime import datetime, timezone

from click.testing import CliRunner

from forecost.adapters.base import UsageEvent
from forecost.commands.doctor_cmd import doctor
from forecost.ledger.sink import SyncLedgerSink


def test_doctor_labels_guessed_spend(ledger_conn, monkeypatch, tmp_path):
    import forecost.commands.doctor_cmd as doctor_module

    sink = SyncLedgerSink()
    sink._conn = ledger_conn
    assert sink.emit(
        UsageEvent(
            event_uid="doctor-guess",
            ts=datetime(2026, 8, 2, tzinfo=timezone.utc),
            source="test",
            model="unknown-future-model",
            tokens_in=1_000_000,
        )
    )
    monkeypatch.setattr(doctor_module, "get_ledger_db", lambda: ledger_conn)
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))

    result = CliRunner().invoke(doctor)

    assert result.exit_code == 0
    assert "guessed" in result.output
    assert "never trigger hard denials" in result.output
    assert "Not published to PyPI" not in result.output
