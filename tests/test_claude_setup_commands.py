from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from forecost.commands.self_test_cmd import self_test
from forecost.commands.setup_cmd import setup


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1] / "plugin"


def test_claude_setup_is_non_mutating_and_checkable():
    runner = CliRunner()
    result = runner.invoke(setup, ["claude", "--dry-run", "--plugin-root", str(_plugin_root())])

    assert result.exit_code == 0
    assert "no files changed" in result.output


def test_claude_self_test_reports_observed_boundary():
    result = CliRunner().invoke(
        self_test, ["claude", "--plugin-root", str(_plugin_root()), "--json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["readiness"] == "OBSERVED"
    assert payload["simulation_passed"] is True
    assert "not provider-side containment" in payload["claim_boundary"]


def test_claude_setup_apply_repair_uninstall_preserves_unrelated_config(tmp_path):
    config = tmp_path / "claude"
    config.mkdir()
    settings = config / "settings.json"
    settings.write_text(
        json.dumps({"theme": "dark", "hooks": {"Notification": [{"hooks": []}]}}),
        encoding="utf-8",
    )
    runner = CliRunner()

    applied = runner.invoke(
        setup,
        ["claude", "--apply", "--config-dir", str(config), "--plugin-root", str(_plugin_root())],
    )
    assert applied.exit_code == 0, applied.output
    installed = json.loads(settings.read_text(encoding="utf-8"))
    assert installed["theme"] == "dark"
    assert "SessionEnd" in installed["hooks"]

    repaired = runner.invoke(
        setup,
        ["claude", "--repair", "--config-dir", str(config), "--plugin-root", str(_plugin_root())],
    )
    assert repaired.exit_code == 0
    assert len(json.loads(settings.read_text())["hooks"]["SessionEnd"]) == 1

    removed = runner.invoke(
        setup,
        [
            "claude",
            "--uninstall",
            "--config-dir",
            str(config),
            "--plugin-root",
            str(_plugin_root()),
        ],
    )
    assert removed.exit_code == 0
    uninstalled = json.loads(settings.read_text(encoding="utf-8"))
    assert uninstalled["theme"] == "dark"
    assert "Notification" in uninstalled["hooks"]
    assert "SessionEnd" not in uninstalled["hooks"]
