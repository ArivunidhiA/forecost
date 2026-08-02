"""Plugin manifests are valid JSON and versions stay in sync (deep-audit FC-009)."""

import json
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # 3.10 fallback (matches forecost/policy/rules.py)
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent


def _load_json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def test_plugin_and_package_versions_agree():
    plugin = _load_json("plugin/.claude-plugin/plugin.json")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    from forecost import __version__

    assert plugin["version"] == pyproject["project"]["version"] == __version__


def test_hooks_json_is_valid_and_uses_documented_vars():
    hooks = _load_json("plugin/hooks/hooks.json")["hooks"]
    # No lifecycle hook may install packages; SessionStart uses only the
    # shared fail-open launcher after the user explicitly installs Forecost.
    cmds = [h["command"] for h in hooks["SessionStart"][0]["hooks"]]
    assert all("bootstrap.sh" not in c for c in cmds)
    assert any("CLAUDE_PLUGIN_ROOT" in c and "run-hook.sh session-start" in c for c in cmds)
    for groups in hooks.values():
        for group in groups:
            for hook in group["hooks"]:
                assert "bootstrap.sh" not in hook["command"]
                assert "run-hook.sh" in hook["command"]
    # Stop is async (documented field).
    assert hooks["Stop"][0]["hooks"][0]["async"] is True


def test_marketplace_json_is_valid():
    mkt = _load_json(".claude-plugin/marketplace.json")
    assert mkt["name"] == "forecost"
    assert mkt["plugins"][0]["source"] == "./plugin"


def test_bootstrap_pin_matches_plugin_version():
    boot = (ROOT / "plugin/scripts/bootstrap.sh").read_text(encoding="utf-8")
    plugin = _load_json("plugin/.claude-plugin/plugin.json")
    assert f'PLUGIN_VERSION="{plugin["version"]}"' in boot
    assert 'INSTALL_SPEC="forecost==$PLUGIN_VERSION"' in boot
    assert "git+" not in boot
    assert "@main" not in boot
