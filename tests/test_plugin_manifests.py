"""Plugin manifests are valid JSON and versions stay in sync (deep-audit FC-009)."""

import json
from pathlib import Path

import tomllib

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
    # SessionStart must bootstrap (CLAUDE_PLUGIN_ROOT) before invoking the venv.
    cmds = [h["command"] for h in hooks["SessionStart"][0]["hooks"]]
    assert any("CLAUDE_PLUGIN_ROOT" in c and "bootstrap.sh" in c for c in cmds)
    assert any("CLAUDE_PLUGIN_DATA" in c and "forecost-hook session-start" in c for c in cmds)
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
