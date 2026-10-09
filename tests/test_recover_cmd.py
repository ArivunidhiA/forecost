"""Tests for `forecost recover` (recovery.jsonl replay)."""

import json
import multiprocessing
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from forecost.adapters.base import content_free_identifier
from forecost.cli import main
from forecost.commands import recover_cmd
from forecost.ledger.db import get_ledger_db


def _recovery_result(label, result):
    return {
        "label": label,
        "replayed": result.replayed,
        "pending": result.pending,
        "skipped": result.skipped,
        "error": result.error,
    }


def _paused_recovery_worker(home, replay_started, release_replay, results):
    os.environ["FORECOST_HOME"] = home
    original_replay = recover_cmd._replay_lines

    def replay_after_release(sink, lines):
        replay_started.set()
        if not release_replay.wait(10):
            raise TimeoutError("test did not release recovery replay")
        return original_replay(sink, lines)

    recover_cmd._replay_lines = replay_after_release
    result = recover_cmd._recover_file(Path(home) / "recovery.jsonl")
    results.put(_recovery_result("first", result))


def _contending_recovery_worker(home, attempted, finished, results):
    os.environ["FORECOST_HOME"] = home
    attempted.set()
    result = recover_cmd._recover_file(Path(home) / "recovery.jsonl")
    results.put(_recovery_result("second", result))
    finished.set()


def _spill_line(event_uid, tokens_out=1_000_000):
    return json.dumps(
        {
            "event_uid": event_uid,
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": "test",
            "model": "claude-opus-4-8",
            "session_uid": "s-rec",
            "workspace_path": "/tmp/p",
            "tokens_in": 0,
            "tokens_out": tokens_out,
            "reported_cost": None,
            "metadata": {},
        }
    )


def test_recover_replays_and_archives(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    # Prime the ledger connection at this home.
    from forecost.ledger import db as ledger_db

    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "ledger.db")
    ledger_db.reset_connection_for_tests()

    (tmp_path / "recovery.jsonl").write_text(_spill_line("r1") + "\n" + _spill_line("r2") + "\n")

    result = CliRunner().invoke(main, ["recover"])
    assert result.exit_code == 0, result.output
    assert "Recovered 2 event(s)" in result.output
    # Events landed in the ledger.
    conn = get_ledger_db()
    n = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
    assert n == 2
    # File archived, so a second run is a no-op replay.
    assert not (tmp_path / "recovery.jsonl").exists()
    archive = tmp_path / "recovery.replayed.jsonl"
    assert archive.exists()
    archived = json.loads(archive.read_text())
    assert archived == {
        "duplicate": 0,
        "record_type": "recovery_replay_summary",
        "replayed": 2,
        "schema_version": 2,
    }
    assert "/tmp/p" not in archive.read_text()
    ledger_db.reset_connection_for_tests()


def test_recover_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    result = CliRunner().invoke(main, ["recover"])
    assert result.exit_code == 0
    assert "No recovery file" in result.output


def test_recover_is_inconclusive_when_declared_queue_cannot_be_statted(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    target = tmp_path / "recovery.jsonl"
    real_lstat = recover_cmd.Path.lstat

    def denied(path):
        if path == target:
            raise PermissionError("synthetic queue denial")
        return real_lstat(path)

    monkeypatch.setattr(recover_cmd.Path, "lstat", denied)

    result = CliRunner().invoke(main, ["recover"])

    assert result.exit_code != 0
    assert "recovery discovery is inconclusive" in result.output
    assert "No recovery file" not in result.output


def test_recover_is_inconclusive_when_home_glob_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    real_glob = recover_cmd.Path.glob

    def denied(path, pattern):
        if path == tmp_path:
            raise PermissionError("synthetic home denial")
        return real_glob(path, pattern)

    monkeypatch.setattr(recover_cmd.Path, "glob", denied)

    result = CliRunner().invoke(main, ["recover"])

    assert result.exit_code != 0
    assert "recovery discovery is inconclusive" in result.output
    assert "No recovery file" not in result.output


def test_recover_keeps_only_failed_lines_for_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    from forecost.ledger import db as ledger_db

    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "ledger.db")
    ledger_db.reset_connection_for_tests()
    malformed = '{"event_uid": "broken"'
    recovery = tmp_path / "recovery.jsonl"
    recovery.write_text(_spill_line("good") + "\n" + malformed + "\n")

    result = CliRunner().invoke(main, ["recover"])

    assert result.exit_code == 0, result.output
    assert "1 still pending" in result.output
    assert recovery.read_text().strip() == malformed
    assert not (tmp_path / "recovery.replayed.jsonl").exists()
    assert get_ledger_db().execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 1
    ledger_db.reset_connection_for_tests()


def test_recover_supports_legacy_write_queue_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    from forecost.ledger import db as ledger_db

    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "ledger.db")
    ledger_db.reset_connection_for_tests()
    legacy = {
        "project_id": 7,
        "timestamp": "2026-03-01T00:00:00Z",
        "model": "claude-opus-4-8",
        "provider": "anthropic",
        "tokens_in": 10,
        "tokens_out": 20,
        "cost_usd": 0.01,
        "metadata": "{}",
        "source": "api",
    }
    (tmp_path / "recovery.jsonl").write_text(json.dumps(legacy) + "\n")

    first = CliRunner().invoke(main, ["recover"])
    assert first.exit_code == 0, first.output
    row = get_ledger_db().execute("SELECT event_uid, ts, source FROM usage_events").fetchone()
    assert row["event_uid"].startswith("event:")
    assert row["source"] == "api"

    # Reintroducing the same legacy record deduplicates through the stable hash.
    (tmp_path / "recovery.jsonl").write_text(json.dumps(legacy) + "\n")
    second = CliRunner().invoke(main, ["recover"])
    assert second.exit_code == 0
    assert "1 already present" in second.output
    assert (tmp_path / "recovery.replayed.1.jsonl").exists()
    ledger_db.reset_connection_for_tests()


def test_recover_preserves_serialized_postings_exactly(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    from forecost.ledger import db as ledger_db

    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "ledger.db")
    ledger_db.reset_connection_for_tests()
    row = json.loads(_spill_line("exact-postings"))
    row["postings"] = [
        {
            "currency": "USD",
            "amount": 123.456,
            "basis": "pricing_table",
            "pricing_version": "historic-snapshot/v1",
        },
        {
            "currency": "QUOTA:synthetic:week",
            "amount": 7.0,
            "basis": "plan_model",
            "pricing_version": "synthetic-plan/v2",
        },
    ]
    (tmp_path / "recovery.jsonl").write_text(json.dumps(row) + "\n")

    result = CliRunner().invoke(main, ["recover"])

    assert result.exit_code == 0, result.output
    postings = [
        tuple(record)
        for record in get_ledger_db()
        .execute("SELECT currency, amount, basis, pricing_version FROM postings ORDER BY currency")
        .fetchall()
    ]
    assert set(postings) == {
        (
            content_free_identifier("currency", "QUOTA:synthetic:week"),
            7.0,
            "plan_model",
            "synthetic-plan/v2",
        ),
        ("USD", 123.456, "pricing_table", "historic-snapshot/v1"),
    }
    ledger_db.reset_connection_for_tests()


def test_spill_published_during_recovery_remains_for_next_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    from forecost.adapters.base import PostingSpec
    from forecost.ledger import db as ledger_db
    from forecost.ledger.writer import _spill_batch

    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "ledger.db")
    ledger_db.reset_connection_for_tests()
    active = tmp_path / "recovery.jsonl"
    active.write_text(_spill_line("old") + "\n")
    original_replay = recover_cmd._replay_lines

    def replay_while_spilling(sink, lines):
        result = original_replay(sink, lines)
        event = recover_cmd._row_to_event(json.loads(_spill_line("new-concurrent-spill")))
        _spill_batch(
            tmp_path / "recovery.jsonl",
            [(event, [PostingSpec("USD", 9.0, "pricing_table", "exact-v1")])],
        )
        return result

    monkeypatch.setattr(recover_cmd, "_replay_lines", replay_while_spilling)
    first = recover_cmd._recover_file(active)

    assert first.pending == 0
    pending = recover_cmd._pending_recovery_paths(tmp_path)
    assert len(pending) == 1
    assert "new-concurrent-spill" in pending[0].read_text()

    monkeypatch.setattr(recover_cmd, "_replay_lines", original_replay)
    second = recover_cmd._recover_file(pending[0])
    assert second.replayed == 1
    rows = (
        get_ledger_db().execute("SELECT event_uid FROM usage_events ORDER BY event_uid").fetchall()
    )
    assert {row[0] for row in rows} == {
        content_free_identifier("event", "new-concurrent-spill"),
        content_free_identifier("event", "old"),
    }
    ledger_db.reset_connection_for_tests()


def test_cross_process_recovery_serializes_rewrite_and_unlink(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    (tmp_path / "recovery.jsonl").write_text(_spill_line("one-cross-process-record") + "\n")
    context = multiprocessing.get_context("spawn")
    replay_started = context.Event()
    release_replay = context.Event()
    contender_attempted = context.Event()
    contender_finished = context.Event()
    results = context.Queue()
    first = context.Process(
        target=_paused_recovery_worker,
        args=(str(tmp_path), replay_started, release_replay, results),
    )
    second = context.Process(
        target=_contending_recovery_worker,
        args=(str(tmp_path), contender_attempted, contender_finished, results),
    )

    first.start()
    try:
        assert replay_started.wait(10)
        second.start()
        assert contender_attempted.wait(10)
        assert not contender_finished.wait(0.25)
    finally:
        release_replay.set()
    first.join(15)
    second.join(15)

    assert first.exitcode == 0
    assert second.exitcode == 0
    outcomes = {item["label"]: item for item in (results.get(timeout=2), results.get(timeout=2))}
    assert outcomes["first"] == {
        "label": "first",
        "replayed": 1,
        "pending": 0,
        "skipped": False,
        "error": None,
    }
    assert outcomes["second"] == {
        "label": "second",
        "replayed": 0,
        "pending": 0,
        "skipped": True,
        "error": None,
    }
    with sqlite3.connect(tmp_path / "ledger.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 1
    assert not (tmp_path / "recovery.jsonl").exists()
    assert len(list(tmp_path.glob("recovery.replayed*.jsonl"))) == 1


def test_recover_processes_current_and_legacy_queue_files(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    from forecost.ledger import db as ledger_db

    monkeypatch.setattr(ledger_db, "LEDGER_PATH", tmp_path / "ledger.db")
    ledger_db.reset_connection_for_tests()
    (tmp_path / "recovery.jsonl").write_text(_spill_line("current") + "\n")
    legacy = {
        "timestamp": "2026-03-01T00:00:00Z",
        "model": "claude-opus-4-8",
        "provider": "anthropic",
        "tokens_in": 10,
        "tokens_out": 20,
        "cost_usd": 0.01,
        "source": "api",
    }
    (tmp_path / "legacy-recovery.jsonl").write_text(json.dumps(legacy) + "\n")

    result = CliRunner().invoke(main, ["recover"])

    assert result.exit_code == 0, result.output
    assert "recovery.jsonl: Recovered 1 event(s)" in result.output
    assert "legacy-recovery.jsonl: Recovered 1 event(s)" in result.output
    assert (tmp_path / "recovery.replayed.jsonl").exists()
    assert (tmp_path / "legacy-recovery.replayed.jsonl").exists()
    assert get_ledger_db().execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 2
    ledger_db.reset_connection_for_tests()


def test_recovery_row_parses_reported_cost_metadata_and_naive_timestamp():
    row = json.loads(_spill_line("reported"))
    row.update(
        {
            "ts": "2026-03-01T12:00:00",
            "reported_cost": {"amount": "1.25", "currency": "USD"},
            "metadata": '{"call_type": "chat"}',
        }
    )

    event = recover_cmd._row_to_event(row)

    assert event.ts == datetime(2026, 3, 1, 12, tzinfo=timezone.utc)
    assert event.reported_cost is not None
    assert event.reported_cost.amount == 1.25
    assert event.metadata == {"call_type": "chat"}


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("metadata", '"not-an-object"', "metadata must be a JSON object"),
        ("ts", None, "missing timestamp"),
    ],
)
def test_recovery_row_rejects_invalid_required_fields(field, value, message):
    row = json.loads(_spill_line("invalid"))
    row[field] = value

    with pytest.raises(ValueError, match=message):
        recover_cmd._row_to_event(row)


def test_rewrite_failed_lines_cleans_temporary_file_on_replace_failure(tmp_path, monkeypatch):
    recovery = tmp_path / "recovery.jsonl"
    recovery.write_text("original\n")

    def fail_replace(source, destination):
        raise OSError("replace denied")

    monkeypatch.setattr(recover_cmd.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace denied"):
        recover_cmd._rewrite_failed_lines(recovery, ["pending"])

    assert recovery.read_text() == "original\n"
    assert list(tmp_path.glob(".recovery-*.tmp")) == []


def test_rewrite_failed_lines_fsyncs_replacement_directory(tmp_path, monkeypatch):
    recovery = tmp_path / "recovery.jsonl"
    recovery.write_text("original\n")
    synced: list[Path] = []
    monkeypatch.setattr(recover_cmd, "_fsync_directory", synced.append)

    recover_cmd._rewrite_failed_lines(recovery, ["pending"])

    assert recovery.read_text() == "pending\n"
    assert synced == [tmp_path]


def test_archive_path_skips_existing_numbered_archives(tmp_path):
    recovery = tmp_path / "recovery.jsonl"
    (tmp_path / "recovery.replayed.jsonl").touch()
    (tmp_path / "recovery.replayed.1.jsonl").touch()

    assert recover_cmd._next_archive_path(recovery).name == "recovery.replayed.2.jsonl"


def test_replay_rejects_non_object_json_line():
    sink = MagicMock()

    replayed, duplicate, failed = recover_cmd._replay_lines(sink, ["[]"])

    assert (replayed, duplicate) == (0, 0)
    assert failed == ["[]"]
    sink.emit.assert_not_called()


def test_flush_failure_retains_every_nonblank_line():
    sink = MagicMock()
    sink.flush.side_effect = RuntimeError("locked")

    retained = recover_cmd._flush_or_retain_all(sink, ["first", "", "second"], ["second"])

    assert retained == ["first", "second"]


def test_recover_file_reports_unreadable_queue(tmp_path):
    unreadable_queue = tmp_path / "recovery.jsonl"
    unreadable_queue.mkdir()

    result = recover_cmd._recover_file(unreadable_queue)

    assert result.error is not None
    assert "could not read queue" in result.error


def test_recovery_discovery_and_open_never_follow_queue_symlink(tmp_path):
    target = tmp_path / "operator-private.jsonl"
    original = _spill_line("must-not-be-replayed") + "\n"
    target.write_text(original)
    recovery = tmp_path / "recovery.jsonl"
    recovery.symlink_to(target)

    assert recover_cmd._pending_recovery_paths(tmp_path) == [recovery]
    result = recover_cmd._recover_file(recovery)

    assert result.error is not None
    assert "could not read queue" in result.error
    assert recovery.is_symlink()
    assert target.read_text() == original
    assert not (tmp_path / "ledger.db").exists()


def test_recovery_discovery_surfaces_nonregular_queue_for_safe_rejection(tmp_path):
    recovery = tmp_path / "recovery.jsonl"
    recovery.mkdir()

    assert recover_cmd._pending_recovery_paths(tmp_path) == [recovery]
    result = recover_cmd._recover_file(recovery)

    assert result.error is not None
    assert "could not read queue" in result.error
    assert recovery.is_dir()


def test_retain_failed_reports_atomic_rewrite_failure(tmp_path, monkeypatch):
    recovery = tmp_path / "recovery.jsonl"
    recovery.write_text("original\n")

    def fail_rewrite(path, lines):
        raise OSError("disk full")

    monkeypatch.setattr(recover_cmd, "_rewrite_failed_lines", fail_rewrite)

    result = recover_cmd._retain_failed(recovery, 1, 2, ["pending"])

    assert result.pending == 1
    assert result.error is not None
    assert "publication durability could not be confirmed" in result.error


def test_archive_failure_is_reported_as_retryable(tmp_path, monkeypatch):
    recovery = tmp_path / "recovery.jsonl"
    original = _spill_line("archive-failure") + "\n"
    recovery.write_text(original)

    def fail_summary(archive, summary):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(recover_cmd, "_write_replay_summary", fail_summary)

    result = recover_cmd._archive_replayed(recovery, 1, 0)

    assert result.archive is None
    assert result.error is not None
    assert "publication durability could not be confirmed" in result.error
    assert recovery.read_text() == original


def test_archive_keeps_raw_queue_when_source_unlink_fails(tmp_path, monkeypatch):
    recovery = tmp_path / "recovery.jsonl"
    original = _spill_line("unlink-failure") + "\n"
    recovery.write_text(original)
    real_unlink = Path.unlink

    def fail_source_unlink(self, *args, **kwargs):
        if self == recovery:
            raise OSError("synthetic unlink failure")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_source_unlink)

    result = recover_cmd._archive_replayed(recovery, 1, 0)

    archive = tmp_path / "recovery.replayed.jsonl"
    assert result.archive == archive
    assert result.error is not None
    assert "raw queue could not be removed" in result.error
    assert recovery.read_text() == original
    assert archive.exists()


def test_archive_reports_uncertain_summary_publication_and_keeps_raw_queue(tmp_path, monkeypatch):
    recovery = tmp_path / "recovery.jsonl"
    original = _spill_line("summary-directory-sync") + "\n"
    recovery.write_text(original)

    def fail_directory_sync(path: Path) -> None:
        raise OSError(f"could not sync {path}")

    monkeypatch.setattr(recover_cmd, "_fsync_directory", fail_directory_sync)

    result = recover_cmd._archive_replayed(recovery, 1, 0)

    assert result.archive is None
    assert result.error is not None
    assert "summary publication durability could not be confirmed" in result.error
    assert recovery.read_text() == original
    archive = tmp_path / "recovery.replayed.jsonl"
    assert json.loads(archive.read_text()) == {
        "duplicate": 0,
        "record_type": "recovery_replay_summary",
        "replayed": 1,
        "schema_version": 2,
    }
    assert not list(tmp_path.glob(".recovery.replayed.jsonl.*.tmp"))


def test_archive_reports_final_unlink_sync_failure_without_recreating_raw_content(
    tmp_path, monkeypatch
):
    recovery = tmp_path / "recovery.jsonl"
    recovery.write_text(_spill_line("unlink-directory-sync") + "\n")
    sync_count = 0

    def fail_second_directory_sync(path: Path) -> None:
        nonlocal sync_count
        assert path == tmp_path
        sync_count += 1
        if sync_count == 2:
            raise OSError("final directory sync failed")

    monkeypatch.setattr(recover_cmd, "_fsync_directory", fail_second_directory_sync)

    result = recover_cmd._archive_replayed(recovery, 1, 0)

    archive = tmp_path / "recovery.replayed.jsonl"
    assert sync_count == 2
    assert result.archive == archive
    assert result.error is not None
    assert "crash durability of that removal could not be confirmed" in result.error
    assert archive.exists()
    assert not recovery.exists()


def test_recover_exits_nonzero_when_any_queue_needs_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    queue = tmp_path / "recovery.jsonl"
    queue.write_text("{}\n")

    def failed_recovery(path):
        return recover_cmd.ReplayResult(path, 0, 0, 1, error="retry required")

    monkeypatch.setattr(recover_cmd, "_recover_file", failed_recovery)

    result = CliRunner().invoke(recover_cmd.recover)

    assert result.exit_code != 0
    assert "ERROR: retry required" in result.output
    assert "One or more recovery queues need an idempotent retry" in result.output
