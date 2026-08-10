import json
import subprocess
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

from scripts.check_release import check_release, release_versions

ROOT = Path(__file__).resolve().parent.parent


def test_all_release_versions_agree():
    versions = release_versions()
    assert len(set(versions.values())) == 1
    version = next(iter(versions.values()))
    assert check_release() == version


def test_base_wheel_contract_includes_claude_plugin_assets():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    force_include = project["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert force_include["plugin"] == "forecost/plugin"
    for relative in (
        "plugin/.claude-plugin/plugin.json",
        "plugin/hooks/hooks.json",
        "plugin/scripts/run-hook.sh",
    ):
        assert (ROOT / relative).is_file()


def test_machine_readable_capabilities_match_supported_surfaces():
    capabilities = json.loads((ROOT / "docs/capabilities.json").read_text(encoding="utf-8"))
    assert capabilities["stores"]["canonical"]["file"] == "ledger.db"
    assert capabilities["stores"]["legacy"]["file"] == "costs.db"
    assert capabilities["interfaces"]["cli"]["legacy_root_aliases"] is False
    assert capabilities["interfaces"]["mcp"]["tools"] == [
        "forecost_list_runs",
        "forecost_get_receipt",
    ]
    assert "read-only" in capabilities["interfaces"]["mcp"]["store"]
    protocols = {
        item["protocol_name"]
        for item in capabilities["adapters"].values()
        if item["protocol_name"] is not None
    }
    assert protocols == {
        "claude_jsonl",
        "litellm",
        "otel_genai",
        "openai_agents",
        "langgraph",
    }


def test_release_check_cli_rejects_wrong_tag():
    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [sys.executable, str(ROOT / "scripts/check_release.py"), "--tag", "v0.0.0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "must equal" in result.stderr


def test_release_check_rejects_unreleased_changelog():
    version = next(iter(release_versions().values()))
    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [sys.executable, str(ROOT / "scripts/check_release.py"), "--tag", f"v{version}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "still marks" in result.stderr
