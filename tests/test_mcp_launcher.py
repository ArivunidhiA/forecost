from __future__ import annotations

import builtins
import sys

import pytest

from forecost.mcp_launcher import main


def test_base_mcp_entrypoint_explains_optional_extra(monkeypatch, capsys):
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
    assert "pip install 'forecost[mcp]'" in capsys.readouterr().err
