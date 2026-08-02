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
