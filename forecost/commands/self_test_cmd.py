"""Offline integration self-tests against exact packaged launchers."""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - fixed packaged launcher, no shell
import tempfile
from pathlib import Path

import click

from forecost.hooks.state import read_heartbeat


def _default_plugin_root() -> Path:
    return Path(__file__).resolve().parents[2] / "plugin"


def _simulate_launcher(root: Path) -> tuple[bool, list[str]]:
    commands = ["session-start", "prompt-submit", "pre-tool", "lifecycle", "stop", "session-end"]
    with tempfile.TemporaryDirectory(prefix="forecost-claude-self-test-") as raw:
        temporary = Path(raw)
        bin_dir = temporary / "venv" / "bin"
        bin_dir.mkdir(parents=True)
        log_path = temporary / "calls.log"
        fake = bin_dir / "forecost-hook"
        fake.write_text(
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$1" >> "$FORECOST_SELF_TEST_LOG"\n'
            "cat >/dev/null\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake.chmod(0o700)
        environment = {
            **os.environ,
            "CLAUDE_PLUGIN_DATA": str(temporary),
            "FORECOST_SELF_TEST_LOG": str(log_path),
        }
        launcher = root / "scripts" / "run-hook.sh"
        for command in commands:
            result = subprocess.run(  # noqa: S603  # nosec B603 - fixed packaged launcher
                [str(launcher), command],
                input='{"hook_event_name":"PostToolUse"}',
                text=True,
                capture_output=True,
                env=environment,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return False, []
        observed = log_path.read_text(encoding="utf-8").splitlines()
        return observed == commands, observed


@click.group(name="self-test")
def self_test() -> None:
    """Run deterministic local integration checks without reading transcripts."""


def _load_plugin(root: Path) -> tuple[dict[str, object], str]:
    try:
        hooks = json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        launcher = (root / "scripts" / "run-hook.sh").read_text(encoding="utf-8")
    except (OSError, KeyError, json.JSONDecodeError) as error:
        raise click.ClickException("cannot read packaged Claude plugin") from error
    if not isinstance(hooks, dict):
        raise click.ClickException("packaged Claude hooks must be an object")
    return hooks, launcher


def _missing_events(hooks: dict[str, object]) -> list[str]:
    required = {
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "SubagentStart",
        "SubagentStop",
        "StopFailure",
        "Stop",
        "SessionEnd",
    }
    return sorted(required - set(hooks))


def _result(root: Path) -> dict[str, object]:
    hooks, launcher = _load_plugin(root)
    missing = _missing_events(hooks)
    launcher_ok = "forecost-hook" in launcher and "|| exit 0" in launcher
    simulation_passed, simulated_commands = _simulate_launcher(root)
    real_observed = read_heartbeat() is not None
    healthy = not missing and launcher_ok and simulation_passed
    return {
        "schema_version": 2,
        "plugin_root": str(root),
        "required_events_present": not missing,
        "missing_events": missing,
        "fail_open_launcher": launcher_ok,
        "simulation_passed": simulation_passed,
        "simulated_commands": simulated_commands,
        "real_hook_heartbeat_observed": real_observed,
        "protection_state": "healthy" if real_observed else "never-ran",
        "readiness": "OBSERVED" if healthy else "NOT OBSERVED",
        "claim_boundary": "offline simulation; not provider-side containment",
    }


def _render_result(result: dict[str, object], json_output: bool) -> None:
    if json_output:
        click.echo(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return
    healthy = result["readiness"] == "OBSERVED"
    if not healthy:
        raise click.ClickException("Claude plugin self-test failed")
    real = (
        "real heartbeat observed"
        if result["real_hook_heartbeat_observed"]
        else "real hook never observed"
    )
    click.echo(f"Claude plugin self-test: simulation passed; {real}; not containment.")


@self_test.command("claude")
@click.option("--plugin-root", type=click.Path(path_type=Path), default=None)
@click.option("--json", "json_output", is_flag=True)
def self_test_claude(plugin_root: Path | None, json_output: bool) -> None:
    """Exercise the exact launcher and separate simulation from real activity."""
    root = (plugin_root or _default_plugin_root()).resolve()
    _render_result(_result(root), json_output)
