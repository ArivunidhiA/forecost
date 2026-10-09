from pathlib import Path

import pytest

from forecost.core import spool


def test_immutable_spool_is_complete_private_and_uniquely_named(tmp_path):
    first = spool.write_immutable_spool(tmp_path / "recovery.jsonl", [{"event_uid": "one"}])
    second = spool.write_immutable_spool(tmp_path / "recovery.jsonl", [{"event_uid": "two"}])

    assert first != second
    assert first.name.startswith("recovery.")
    assert first.read_text() == '{"event_uid":"one"}\n'
    assert second.read_text() == '{"event_uid":"two"}\n'
    assert not list(tmp_path.glob(".recovery-spill-*.tmp"))


def test_immutable_spool_cleans_temp_file_when_publish_fails(tmp_path, monkeypatch):
    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("publish denied")

    monkeypatch.setattr(spool.os, "replace", fail_replace)
    home = tmp_path / "home"

    with pytest.raises(OSError, match="publish denied"):
        spool.write_immutable_spool(home / "recovery.jsonl", [{"event_uid": "one"}])

    assert not list(home.glob(".recovery-spill-*.tmp"))
    assert not list(home.glob("recovery.*.jsonl"))


def test_immutable_spool_fsyncs_published_directory(tmp_path, monkeypatch):
    synced: list[Path] = []
    monkeypatch.setattr(spool, "_fsync_directory", synced.append)

    published = spool.write_immutable_spool(tmp_path / "recovery.jsonl", [{"event_uid": "durable"}])

    assert published.parent == tmp_path
    assert synced == [tmp_path]


def test_immutable_spool_reports_directory_sync_failure_but_keeps_complete_copy(
    tmp_path, monkeypatch
):
    def fail_directory_sync(path: Path) -> None:
        raise OSError(f"could not sync {path}")

    monkeypatch.setattr(spool, "_fsync_directory", fail_directory_sync)

    with pytest.raises(OSError, match="could not sync"):
        spool.write_immutable_spool(tmp_path / "recovery.jsonl", [{"event_uid": "uncertain"}])

    published = list(tmp_path.glob("recovery.*.jsonl"))
    assert len(published) == 1
    assert published[0].read_text() == '{"event_uid":"uncertain"}\n'
    assert not list(tmp_path.glob(".recovery-spill-*.tmp"))
