from __future__ import annotations

import multiprocessing
import os

import pytest
from click.testing import CliRunner

from forecost.commands.statusline_cmd import statusline
from forecost.core.paths import UnsafeDataPathError
from forecost.hooks import handlers
from forecost.hooks import state as state_mod
from forecost.hooks.state import (
    append_settlement_marker,
    clear_settlements,
    pending_settlements,
    read_heartbeat,
    record_heartbeat,
    snapshot_settlements,
)


def _snapshot_then_clear_worker(home, snapshot_ready, append_done, result_queue):
    os.environ["FORECOST_HOME"] = home
    snapshot = snapshot_settlements()
    snapshot_ready.set()
    if not append_done.wait(10):
        result_queue.put("append-timeout")
        return
    result_queue.put(clear_settlements(snapshot))


def _append_after_snapshot_worker(home, snapshot_ready, append_done):
    os.environ["FORECOST_HOME"] = home
    if not snapshot_ready.wait(10):
        return
    append_settlement_marker({"session_id": "new-concurrent-session"})
    append_done.set()


def test_session_end_fsyncs_only_content_free_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path / "home"))
    handlers.handle_session_end(
        {
            "session_id": "raw-session",
            "transcript_path": "/private/raw/transcript.jsonl",
            "prompt": "NEVER-PERSIST",
        }
    )
    assert pending_settlements() == 1
    blob = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "home" / "hooks").iterdir()
        if path.is_file()
    )
    assert "raw-session" not in blob
    assert "transcript" not in blob
    assert "NEVER-PERSIST" not in blob


def test_statusline_exposes_never_ran_and_observed_states(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path / "home"))
    import forecost.ledger.db as ledger_db

    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "home" / "ledger.db")
    monkeypatch.setattr(ledger_db, "_conn", None)
    first = CliRunner().invoke(statusline)
    assert first.exit_code == 0
    assert "NOT OBSERVED" in first.output
    handlers.handle_session_end({"session_id": "s"})
    heartbeat = read_heartbeat()
    assert heartbeat is not None
    assert heartbeat["readiness"] == "OBSERVED"
    second = CliRunner().invoke(statusline)
    assert "OBSERVED" in second.output


def test_settlement_append_refuses_symlink_without_clobbering_target(tmp_path, monkeypatch):
    home = tmp_path / "home"
    hooks = home / "hooks"
    hooks.mkdir(parents=True)
    (home / ".forecost-owned").write_text("")
    (hooks / ".forecost-owned").write_text("")
    target = tmp_path / "operator.txt"
    target.write_text("preserve", encoding="utf-8")
    (hooks / "settlement-required.jsonl").symlink_to(target)
    monkeypatch.setenv("FORECOST_HOME", str(home))

    with pytest.raises(UnsafeDataPathError, match="refusing symlinked"):
        append_settlement_marker({"session_id": "s"})

    assert target.read_text(encoding="utf-8") == "preserve"


def test_hook_state_fsyncs_create_replace_append_and_unlink_names(tmp_path, monkeypatch):
    home = tmp_path / "home"
    hooks = home / "hooks"
    monkeypatch.setenv("FORECOST_HOME", str(home))
    synced: list[object] = []
    monkeypatch.setattr(state_mod, "_fsync_directory", synced.append)

    record_heartbeat("SessionStart")
    append_settlement_marker({"session_id": "s"})
    clear_settlements(snapshot_settlements())

    assert tmp_path in synced  # newly created home name
    assert home in synced  # newly created hooks name
    assert synced.count(hooks) >= 3  # heartbeat replace, marker create, marker unlink


def test_hook_append_reports_directory_sync_failure_but_keeps_complete_marker(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    hooks = home / "hooks"
    hooks.mkdir(parents=True)
    (home / ".forecost-owned").write_text("")
    (hooks / ".forecost-owned").write_text("")
    monkeypatch.setenv("FORECOST_HOME", str(home))

    def fail_directory_sync(_path):
        raise OSError("directory sync failed")

    monkeypatch.setattr(state_mod, "_fsync_directory", fail_directory_sync)

    with pytest.raises(OSError, match="directory sync failed"):
        append_settlement_marker({"session_id": "s"})

    marker = hooks / "settlement-required.jsonl"
    assert marker.read_text(encoding="utf-8").endswith("\n")


def test_settlement_ack_preserves_markers_appended_after_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path / "home"))
    append_settlement_marker({"session_id": "observed"})
    observed = snapshot_settlements()

    append_settlement_marker({"session_id": "arrived-during-reconciliation"})

    assert clear_settlements(observed) is True
    assert pending_settlements() == 1


def test_stale_settlement_snapshot_cannot_ack_a_new_queue_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path / "home"))
    append_settlement_marker({"session_id": "observed"})
    first_reconciler = snapshot_settlements()
    second_reconciler = snapshot_settlements()
    append_settlement_marker({"session_id": "new"})

    assert clear_settlements(first_reconciler) is True
    assert clear_settlements(second_reconciler) is False
    assert pending_settlements() == 1


def test_cross_process_settlement_ack_preserves_concurrent_append(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("FORECOST_HOME", str(home))
    append_settlement_marker({"session_id": "observed-before-reconciliation"})
    context = multiprocessing.get_context("spawn")
    snapshot_ready = context.Event()
    append_done = context.Event()
    result_queue = context.Queue()
    clearer = context.Process(
        target=_snapshot_then_clear_worker,
        args=(str(home), snapshot_ready, append_done, result_queue),
    )
    appender = context.Process(
        target=_append_after_snapshot_worker,
        args=(str(home), snapshot_ready, append_done),
    )

    clearer.start()
    appender.start()
    clearer.join(15)
    appender.join(15)

    assert clearer.exitcode == 0
    assert appender.exitcode == 0
    assert result_queue.get(timeout=2) is True
    assert pending_settlements() == 1
