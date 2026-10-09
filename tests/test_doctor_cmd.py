import json
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


def test_doctor_json_reports_explicit_readiness(ledger_conn, monkeypatch, tmp_path):
    import forecost.commands.doctor_cmd as doctor_module

    monkeypatch.setattr(doctor_module, "get_ledger_db", lambda: ledger_conn)
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))

    result = CliRunner().invoke(doctor, ["--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["product_state"] == "UNRELEASED EXPERIMENTAL"
    assert payload["release_hold"] is True
    assert payload["readiness"]["claude_code"] == "NOT OBSERVED"
    assert payload["readiness"]["distributed_enforcement"] == "NOT OBSERVED"
    assert payload["stores"]["canonical"]["path"].endswith("ledger.db")
    assert payload["stores"]["canonical"]["role"] == "unreleased experimental receipt ledger"
    assert payload["stores"]["legacy"]["path"].endswith("costs.db")
    assert payload["stores"]["legacy"]["role"] == "unsupported v0.2 compatibility"
    limitations = " ".join(payload["limitations"])
    assert "legacy SDK can persist project names, paths, and metadata" in limitations
    assert "configured state outside that root" in limitations
    assert "same OS user" in limitations
