from __future__ import annotations

import builtins
import sys

import pytest

from forecost.mcp_launcher import main


def test_optional_mcp_module_explains_extra_and_launch_command(monkeypatch, capsys):
    real_import = builtins.__import__
    monkeypatch.delitem(sys.modules, "forecost.mcp.server", raising=False)

    def without_mcp(name, *args, **kwargs):
        if name.startswith("mcp"):
            raise ModuleNotFoundError("No module named 'mcp'", name="mcp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_mcp)
    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 2
    error = capsys.readouterr().err
    assert "pip install 'forecost[mcp]'" in error
    assert "python -m forecost.mcp_launcher" in error


def test_base_package_does_not_advertise_optional_mcp_console_script():
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert "forecost-mcp =" not in pyproject.read_text(encoding="utf-8")
