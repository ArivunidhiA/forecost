import subprocess
import sys


def _loaded_modules(command: str) -> set[str]:
    script = (
        "import sys; "
        "from click.testing import CliRunner; "
        "from forecost.cli import main; "
        f"result=CliRunner().invoke(main, {command!r}.split()); "
        "assert result.exit_code == 0, result.output; "
        "print('\\n'.join(sys.modules))"
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and inline test script
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    return set(result.stdout.splitlines())


def test_help_does_not_import_legacy_forecasting_stack():
    modules = _loaded_modules("--help")
    assert "forecost.forecaster" not in modules
    assert "statsmodels" not in modules
    assert "numpy" not in modules


def test_ledger_command_does_not_import_legacy_forecasting_stack(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    modules = _loaded_modules("ledger status")
    assert "forecost.forecaster" not in modules
    assert "statsmodels" not in modules
    assert "numpy" not in modules
