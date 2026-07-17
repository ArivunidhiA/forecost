"""Tests for the forecost purge command."""

from click.testing import CliRunner

from forecost.cli import main


def test_purge_removes_forecost_dir(tmp_path, monkeypatch):
    """Purge deletes ~/.forecost/ directory."""
    fake_home = tmp_path / "home"
    forecost_dir = fake_home / ".forecost"
    forecost_dir.mkdir(parents=True)
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
    forecost_dir.mkdir(parents=True)

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
    forecost_dir.mkdir(parents=True)

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
