import pytest
from click.testing import CliRunner

from forecost import __version__
from forecost.cli import main


@pytest.fixture
def cli_runner():
    return CliRunner()


def test_cli_commands_exist(cli_runner):
    result = cli_runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "ingest" in result.output
    assert "ledger" in result.output
    assert "reconcile" in result.output
    assert "legacy" in result.output
    assert "forecast" not in result.output


def test_legacy_commands_are_explicitly_quarantined(cli_runner):
    result = cli_runner.invoke(main, ["legacy", "--help"])
    assert result.exit_code == 0
    assert "forecast" in result.output
    assert "init" in result.output
    assert "legacy costs.db" in result.output
    assert "serve" not in result.output


@pytest.mark.parametrize("command", ["forecast", "init", "serve", "status"])
def test_legacy_commands_have_no_hidden_root_alias(cli_runner, command):
    result = cli_runner.invoke(main, [command])
    assert result.exit_code == 2
    assert "No such command" in result.output


def test_current_help_declares_store_boundaries(cli_runner):
    result = cli_runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "canonical ledger.db" in result.output
    assert "reads legacy costs.db; appends canonical ledger.db" in result.output


def test_loaded_command_help_declares_its_store(cli_runner):
    result = cli_runner.invoke(main, ["runs", "--help"])
    assert result.exit_code == 0
    assert "Store boundary: canonical ledger.db (read-only)." in result.output


def test_legacy_smart_upload_path_is_retired(cli_runner):
    result = cli_runner.invoke(main, ["legacy", "init", "--help"])
    assert result.exit_code == 0
    assert "--smart" not in result.output


def test_forecost_version(cli_runner):
    result = cli_runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_forecost_init_in_temp_directory(cli_runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("forecost.db._DB_PATH", tmp_path / "costs.db")
    monkeypatch.setattr("forecost.db._conn", None)
    (tmp_path / ".forecost").mkdir(exist_ok=True)
    result = cli_runner.invoke(main, ["legacy", "init"])
    assert result.exit_code == 0
    assert (tmp_path / ".forecost.toml").exists()
    assert "forecost initialized" in result.output or "initialized" in result.output.lower()
