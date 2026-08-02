"""Offline self-tests for the packaged Claude plugin boundary."""

from __future__ import annotations

import json
from pathlib import Path

import click


def _default_plugin_root() -> Path:
    return Path(__file__).resolve().parents[2] / "plugin"


@click.group(name="self-test")
def self_test() -> None:
    """Run deterministic local integration checks without reading transcripts."""


@self_test.command("claude")
@click.option("--plugin-root", type=click.Path(path_type=Path), default=None)
@click.option("--json", "json_output", is_flag=True)
def self_test_claude(plugin_root: Path | None, json_output: bool) -> None:
    """Validate the exact hook launcher package and report honest readiness."""
    root = (plugin_root or _default_plugin_root()).resolve()
    hooks_path = root / "hooks" / "hooks.json"
    launcher_path = root / "scripts" / "run-hook.sh"
    try:
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))["hooks"]
        launcher = launcher_path.read_text(encoding="utf-8")
    except (OSError, KeyError, json.JSONDecodeError) as error:
        raise click.ClickException("cannot read packaged Claude plugin") from error
    required_events = {"SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "SessionEnd"}
    missing = sorted(required_events - set(hooks))
    launcher_ok = "forecost-hook" in launcher and "|| exit 0" in launcher
    result = {
        "schema_version": 1,
        "plugin_root": str(root),
        "required_events_present": not missing,
        "missing_events": missing,
        "fail_open_launcher": launcher_ok,
        "readiness": "OBSERVED" if not missing and launcher_ok else "NOT OBSERVED",
        "claim_boundary": "local fail-open observation; not provider-side containment",
    }
    if json_output:
        click.echo(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return
    if result["readiness"] != "OBSERVED":
        raise click.ClickException(
            "Claude plugin self-test failed: " + ", ".join(missing or ["launcher"])
        )
    click.echo(
        "Claude plugin self-test: OBSERVED (local fail-open; not provider-side containment)."
    )
