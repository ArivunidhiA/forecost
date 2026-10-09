from __future__ import annotations

import os

from click.testing import CliRunner

from forecost.commands import privacy_cmd
from forecost.commands.privacy_cmd import privacy


def test_privacy_verify_streams_files_larger_than_old_limit(tmp_path):
    target = tmp_path / "large.bin"
    with target.open("wb") as stream:
        stream.seek(33 * 1024 * 1024)
        stream.write(b"FORECOST-PRIVACY-CANARY")

    result = CliRunner().invoke(privacy, ["verify", "--home", str(tmp_path)])

    assert result.exit_code != 0
    assert "privacy canary found" in result.output


def test_privacy_verify_finds_canary_across_chunk_boundary(tmp_path):
    canary = b"boundary-canary"
    target = tmp_path / "boundary.bin"
    prefix = b"x" * (privacy_cmd._SCAN_CHUNK_BYTES - 5)
    target.write_bytes(prefix + canary)

    result = CliRunner().invoke(
        privacy,
        ["verify", "--home", str(tmp_path), "--canary", canary.decode()],
    )

    assert result.exit_code != 0
    assert "privacy canary found" in result.output


def test_privacy_verify_is_inconclusive_on_unreadable_owned_file(tmp_path, monkeypatch):
    target = tmp_path / "ledger.db"
    target.write_bytes(b"safe")
    real_open = os.open

    def denied(path, flags, *args, **kwargs):
        if os.fspath(path) == os.fspath(target):
            raise PermissionError("synthetic denial")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(privacy_cmd.os, "open", denied)

    result = CliRunner().invoke(privacy, ["verify", "--home", str(tmp_path)])

    assert result.exit_code != 0
    assert "privacy scan inconclusive" in result.output


def test_privacy_verify_is_inconclusive_on_unreadable_owned_directory(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "hidden.db").write_bytes(b"FORECOST-PRIVACY-CANARY")
    real_scandir = os.scandir

    def denied(path):
        if os.fspath(path) == os.fspath(blocked):
            raise PermissionError("synthetic directory denial")
        return real_scandir(path)

    monkeypatch.setattr(privacy_cmd.os, "scandir", denied)

    result = CliRunner().invoke(privacy, ["verify", "--home", str(tmp_path)])

    assert result.exit_code != 0
    assert "privacy scan inconclusive" in result.output
    assert "1 unreadable" in result.output


def test_privacy_verify_is_inconclusive_when_root_cannot_be_statted(tmp_path, monkeypatch):
    real_exists = privacy_cmd.Path.exists

    def denied(path):
        if path == tmp_path:
            raise PermissionError("synthetic root denial")
        return real_exists(path)

    monkeypatch.setattr(privacy_cmd.Path, "exists", denied)

    result = CliRunner().invoke(privacy, ["verify", "--home", str(tmp_path)])

    assert result.exit_code != 0
    assert result.exception is not None
    assert "privacy scan inconclusive" in result.output
    assert "1 unreadable" in result.output


def test_privacy_verify_reports_bytes_and_no_skips(tmp_path):
    (tmp_path / "ledger.db").write_bytes(b"safe")

    result = CliRunner().invoke(privacy, ["verify", "--home", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "4 byte(s), 0 skipped/unreadable" in result.output


def test_privacy_verify_is_inconclusive_on_symlink_in_scanned_root(tmp_path):
    outside = tmp_path.parent / "outside-privacy-canary.txt"
    outside.write_text("FORECOST-PRIVACY-CANARY", encoding="utf-8")
    (tmp_path / "linked-state").symlink_to(outside)

    result = CliRunner().invoke(privacy, ["verify", "--home", str(tmp_path)])

    assert result.exit_code != 0
    assert "privacy scan inconclusive" in result.output
    assert "1 skipped" in result.output
