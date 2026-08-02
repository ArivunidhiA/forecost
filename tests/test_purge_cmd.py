"""Tests for the forecost purge command."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from forecost.cli import main
from forecost.core.paths import ensure_private_dir


def test_purge_removes_forecost_dir(tmp_path, monkeypatch):
    """Purge deletes ~/.forecost/ directory."""
    fake_home = tmp_path / "home"
    forecost_dir = fake_home / ".forecost"
    ensure_private_dir(forecost_dir)
    (forecost_dir / "costs.db").write_text("fake")
    (forecost_dir / "error.log").write_text("fake")

    monkeypatch.setenv("FORECOST_HOME", str(forecost_dir))
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["purge", "--yes"])

    assert result.exit_code == 0
    assert not forecost_dir.exists()
    assert "Purge complete" in result.output


def test_purge_removes_local_toml(tmp_path, monkeypatch):
    """Purge also removes .forecost.toml in cwd."""
    fake_home = tmp_path / "home"
    forecost_dir = fake_home / ".forecost"
    ensure_private_dir(forecost_dir)

    monkeypatch.setenv("FORECOST_HOME", str(forecost_dir))
    monkeypatch.chdir(tmp_path)

    local_toml = tmp_path / ".forecost.toml"
    local_toml.write_text("[project]\nname = 'test'\n")

    runner = CliRunner()
    result = runner.invoke(main, ["purge", "--yes"])

    assert result.exit_code == 0
    assert not local_toml.exists()


def test_purge_keep_config(tmp_path, monkeypatch):
    """Purge --keep-config preserves .forecost.toml."""
    fake_home = tmp_path / "home"
    forecost_dir = fake_home / ".forecost"
    ensure_private_dir(forecost_dir)

    monkeypatch.setenv("FORECOST_HOME", str(forecost_dir))
    monkeypatch.chdir(tmp_path)

    local_toml = tmp_path / ".forecost.toml"
    local_toml.write_text("[project]\nname = 'test'\n")

    runner = CliRunner()
    result = runner.invoke(main, ["purge", "--keep-config", "--yes"])

    assert result.exit_code == 0
    assert not forecost_dir.exists()
    assert local_toml.exists()


def test_purge_nothing_to_purge(tmp_path, monkeypatch):
    """Purge with no data shows informative message."""
    fake_home = tmp_path / "home"
    forecost_dir = fake_home / ".forecost"  # Does not exist

    monkeypatch.setenv("FORECOST_HOME", str(forecost_dir))
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["purge", "--yes"])

    assert result.exit_code == 0
    assert "Nothing to purge" in result.output


@pytest.mark.parametrize("unsafe", [Path("/"), Path.home(), Path("relative/home")])
def test_purge_refuses_broad_or_relative_targets(unsafe, tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(unsafe))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["purge", "--yes"])

    assert result.exit_code != 0
    assert "Refusing unsafe purge target" in result.output


def test_purge_refuses_current_workspace_and_ancestor(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    marker = workspace / "ledger.db"
    marker.write_text("must survive")
    monkeypatch.chdir(workspace)

    for target in (workspace, tmp_path):
        monkeypatch.setenv("FORECOST_HOME", str(target))
        result = CliRunner().invoke(main, ["purge", "--yes"])
        assert result.exit_code != 0
        assert "Refusing unsafe purge target" in result.output
    assert marker.read_text() == "must survive"


def test_purge_refuses_symlinked_home(tmp_path, monkeypatch):
    actual = tmp_path / "actual"
    actual.mkdir()
    marker = actual / "ledger.db"
    marker.write_text("must survive")
    link = tmp_path / "linked-home"
    link.symlink_to(actual, target_is_directory=True)
    monkeypatch.setenv("FORECOST_HOME", str(link))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["purge", "--yes"])

    assert result.exit_code != 0
    assert "symlink" in result.output
    assert marker.exists()


def test_purge_preserves_unknown_entries(tmp_path, monkeypatch):
    forecost_dir = tmp_path / "home" / ".forecost"
    ensure_private_dir(forecost_dir)
    (forecost_dir / "ledger.db").write_text("forecost")
    user_file = forecost_dir / "notes.txt"
    user_file.write_text("not owned by forecost")
    monkeypatch.setenv("FORECOST_HOME", str(forecost_dir))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["purge", "--yes"])

    assert result.exit_code == 0
    assert user_file.exists()
    assert "Preserved unknown entries" in result.output


def test_purge_removes_only_strict_recovery_spool_names(tmp_path, monkeypatch):
    forecost_dir = tmp_path / "home" / ".forecost"
    ensure_private_dir(forecost_dir)
    spool_id = "a" * 32
    active = forecost_dir / f"recovery.123.456.{spool_id}.jsonl"
    archived = forecost_dir / f"recovery.123.456.{spool_id}.replayed.jsonl"
    unrelated = forecost_dir / "recovery.personal.jsonl"
    for path in (active, archived, unrelated):
        path.write_text("synthetic")
    monkeypatch.setenv("FORECOST_HOME", str(forecost_dir))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["purge", "--yes"])

    assert result.exit_code == 0
    assert not active.exists()
    assert not archived.exists()
    assert unrelated.exists()


def test_purge_refuses_data_home_that_is_a_file(tmp_path, monkeypatch):
    data_home = tmp_path / "forecost-data"
    data_home.write_text("not a directory")
    monkeypatch.setenv("FORECOST_HOME", str(data_home))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["purge", "--yes"])

    assert result.exit_code != 0
    assert "Refusing unsafe purge target" in result.output
    assert "not a directory" in result.output
    assert data_home.read_text() == "not a directory"


def test_purge_refuses_unmarked_custom_directory(tmp_path, monkeypatch):
    custom = tmp_path / "shared-data"
    custom.mkdir()
    coincidental = custom / "ledger.db"
    coincidental.write_text("not forecost")
    monkeypatch.setenv("FORECOST_HOME", str(custom))
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["purge", "--yes"])

    assert result.exit_code != 0
    assert "ownership marker" in result.output
    assert coincidental.read_text() == "not forecost"
