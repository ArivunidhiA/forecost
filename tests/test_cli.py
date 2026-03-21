import pytest
from click.testing import CliRunner

from llmcast.cli import main


@pytest.fixture
def cli_runner():
    return CliRunner()


def test_cli_commands_exist(cli_runner):
    result = cli_runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.output
    assert "forecast" in result.output
    assert "status" in result.output
    assert "track" in result.output
    assert "serve" in result.output


def test_llmcast_version(cli_runner):
    result = cli_runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output or "llmcast" in result.output.lower()


def test_llmcast_init_in_temp_directory(cli_runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("llmcast.db._DB_PATH", tmp_path / "costs.db")
    monkeypatch.setattr("llmcast.db._conn", None)
    (tmp_path / ".llmcast").mkdir(exist_ok=True)
    result = cli_runner.invoke(main, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / ".llmcast.toml").exists()
    assert "llmcast initialized" in result.output or "initialized" in result.output.lower()
