"""Public CLI surface journeys: lab, receipt, envelope, doctor (in-process, real ledger)."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from forecost.cli import main
from forecost.ledger import db as ledger_db


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "ledger.db")
    ledger_db.reset_connection_for_tests()
    yield tmp_path
    ledger_db.reset_connection_for_tests()


def _invoke(*args: str, ok: bool = True):
    result = CliRunner().invoke(main, list(args))
    if ok:
        assert result.exit_code == 0, result.output
    return result


def _run_id(output: str) -> str:
    match = re.search(r"^Run: (\S+)", output, re.M)
    assert match, output
    return match.group(1)


def test_lab_demo_is_deterministic_and_receipt_renders_in_every_format(home, tmp_path):
    lab = tmp_path / "lab.db"
    first = _invoke("lab", "demo", "--ledger-path", str(lab))
    second = _invoke("lab", "demo", "--ledger-path", str(tmp_path / "lab2.db"))
    assert _run_id(first.output) == _run_id(second.output)

    _invoke("lab", "demo", "--ledger-path", str(home / "ledger.db"))
    run = _run_id(first.output)
    text = _invoke("receipt", run).output
    assert "Evidence profiles" in text
    payload = json.loads(_invoke("receipt", run, "--json-output").output)
    assert isinstance(payload, dict)
    assert _invoke("receipt", run, "--markdown").output.startswith("# Forecost run receipt")


def test_receipt_for_unknown_run_fails_cleanly(home):
    result = _invoke("receipt", "run:does-not-exist", ok=False)
    assert result.exit_code != 0
    assert "Traceback" not in result.output


def test_lab_chaos_scales_with_branches(home, tmp_path):
    small = _invoke("lab", "chaos", "--branches", "2", "--ledger-path", str(tmp_path / "a.db"))
    large = _invoke("lab", "chaos", "--branches", "6", "--ledger-path", str(tmp_path / "b.db"))
    assert "branches: 2" in small.output
    assert "branches: 6" in large.output
    sizes = [
        sqlite3.connect(tmp_path / n).execute("SELECT COUNT(*) FROM causal_spans").fetchone()[0]
        for n in ("a.db", "b.db")
    ]
    assert sizes[1] > sizes[0]


def test_lab_rejects_out_of_range_branches(home, tmp_path):
    result = _invoke(
        "lab", "chaos", "--branches", "0", "--ledger-path", str(tmp_path / "x.db"), ok=False
    )
    assert result.exit_code == 2


def _create_scope(name: str = "team", capacity: int = 1_000_000) -> None:
    _invoke(
        "envelope", "create", name, "--dimension", "money_usd", "--capacity-micros", str(capacity)
    )


def _reservation_id(output: str) -> str:
    match = re.search(r"(reservation:[0-9a-f]+)", output)
    assert match, output
    return match.group(1)


def test_envelope_reserve_settle_conserves_capacity(home):
    _create_scope()
    reserved = _invoke("envelope", "reserve", "team", "--amount-micros", "400000", "--key", "k1")
    assert "granted=400000" in reserved.output
    again = _invoke("envelope", "reserve", "team", "--amount-micros", "400000", "--key", "k1")
    assert _reservation_id(again.output) == _reservation_id(reserved.output)  # idempotent key
    assert "reserved=400000" in _invoke("envelope", "balance", "team").output
    settled = _invoke(
        "envelope", "settle", _reservation_id(reserved.output), "--used-micros", "150000"
    )
    assert "used=150000" in settled.output
    balance = _invoke("envelope", "balance", "team").output
    assert "settled=150000" in balance
    assert "available=850000" in balance
    assert "conserved=true" in balance


def test_envelope_release_returns_capacity_and_overcommit_is_refused(home):
    _create_scope(capacity=500_000)
    held = _invoke("envelope", "reserve", "team", "--amount-micros", "500000", "--key", "a")
    refused = _invoke("envelope", "reserve", "team", "--amount-micros", "1", "--key", "b", ok=False)
    assert "Traceback" not in refused.output
    _invoke("envelope", "release", _reservation_id(held.output))
    assert "available=500000" in _invoke("envelope", "balance", "team").output


def test_envelope_split_and_finalize_child(home):
    _create_scope(capacity=1_000_000)
    split = _invoke(
        "envelope", "split", "team", "child", "--capacity-micros", "300000", "--key", "child-key"
    )
    child = re.search(r"(resource-scope:[0-9a-f]+)", split.output)
    assert child, split.output
    assert "available=700000" in _invoke("envelope", "balance", "team").output
    _invoke("envelope", "finalize-child", child.group(1))
    assert "conserved=true" in _invoke("envelope", "balance", "team").output


def test_envelope_recover_with_nothing_live(home):
    assert "Expired 0 reservation(s)." in _invoke("envelope", "recover").output


def test_doctor_json_and_legacy_raw_row_warning(home):
    report = json.loads(_invoke("doctor", "--json").output)
    assert report["stores"]["legacy"]["present"] is False

    legacy = Path(home) / "costs.db"
    conn = sqlite3.connect(legacy)
    conn.executescript(
        """
        CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, path TEXT, metadata TEXT);
        CREATE TABLE usage_logs (id INTEGER PRIMARY KEY, project_id INTEGER, metadata TEXT);
        INSERT INTO projects VALUES (1, '/Users/x/client/app', '/Users/x/client/app', NULL);
        """
    )
    conn.commit()
    conn.close()
    text = _invoke("doctor").output
    assert "1 row(s) with raw paths" in text
    assert "forecost legacy scrub" in text
