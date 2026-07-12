"""Direct (in-process) tests of the forecost-hook fastpath dispatcher, for the
coverage the subprocess tests in test_hooks.py can't provide."""

import io
import json

import pytest

import forecost.ledger.db as ledger_db
from forecost.hooks import fastpath


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "ledger.db")
    monkeypatch.setattr(ledger_db, "_conn", None)
    yield
    ledger_db.reset_connection_for_tests()


def test_read_payload_valid(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"a": 1})))
    assert fastpath._read_payload() == {"a": 1}


def test_read_payload_empty(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("   "))
    assert fastpath._read_payload() == {}


def test_read_payload_malformed(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json {{{"))
    assert fastpath._read_payload() is None


def test_dispatch_prints_result(capsys):
    fastpath._dispatch("session-start", {"session_id": "s", "cwd": "/tmp/p"})
    # session-start returns {}, so nothing is printed
    assert capsys.readouterr().out == ""


def test_dispatch_preflight_prints_on_scope_maximizer(capsys):
    fastpath._dispatch(
        "prompt-submit",
        {
            "session_id": "s",
            "cwd": "/tmp/p",
            "prompt_id": "p",
            "prompt": "refactor the entire module",
        },
    )
    out = capsys.readouterr().out
    assert "hookSpecificOutput" in out


def test_main_unknown_command_exits_zero(monkeypatch):
    monkeypatch.setattr("sys.argv", ["forecost-hook", "bogus"])
    with pytest.raises(SystemExit) as e:
        fastpath.main()
    assert e.value.code == 0


def test_main_no_command_exits_zero(monkeypatch):
    monkeypatch.setattr("sys.argv", ["forecost-hook"])
    with pytest.raises(SystemExit) as e:
        fastpath.main()
    assert e.value.code == 0


def test_main_malformed_stdin_exits_zero(monkeypatch):
    monkeypatch.setattr("sys.argv", ["forecost-hook", "prompt-submit"])
    monkeypatch.setattr("sys.stdin", io.StringIO("not json {{{"))
    with pytest.raises(SystemExit) as e:
        fastpath.main()
    assert e.value.code == 0


def test_main_handler_exception_fails_open(monkeypatch):
    monkeypatch.setattr("sys.argv", ["forecost-hook", "prompt-submit"])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "x"})))

    def _boom(payload):
        raise RuntimeError("handler blew up")

    monkeypatch.setattr("forecost.hooks.handlers.handle_preflight", _boom)
    with pytest.raises(SystemExit) as e:
        fastpath.main()
    assert e.value.code == 0  # fail-open: the hook never propagates the error


def test_main_success_exits_zero(monkeypatch):
    monkeypatch.setattr("sys.argv", ["forecost-hook", "session-start"])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "s", "cwd": "/tmp/p"})))
    with pytest.raises(SystemExit) as e:
        fastpath.main()
    assert e.value.code == 0
