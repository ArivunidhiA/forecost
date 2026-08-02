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
    assert "not provider-side containment" in payload["claim_boundary"]
