"""Reversible Claude integration setup with isolated-config testability."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

import click

from forecost.hooks.state import HOOK_PROTOCOL_VERSION


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[2] / "plugin"


def _config_path(config_dir: Path | None) -> Path:
    return (config_dir or (Path.home() / ".claude")) / "settings.json"


def _protocol_path(settings_path: Path) -> Path:
    return settings_path.with_name("forecost-hook.json")


def _command(name: str) -> str:
    return f"{shlex.quote(sys.executable)} -m forecost.hooks.fastpath {shlex.quote(name)}"


def _managed_hooks() -> dict[str, list[dict[str, object]]]:
    lifecycle = {"type": "command", "command": _command("lifecycle"), "timeout": 5, "async": True}

    def hook(command: str, timeout: int, *, asynchronous: bool = False) -> list[dict[str, object]]:
        item: dict[str, object] = {
            "type": "command",
            "command": _command(command),
            "timeout": timeout,
        }
        if asynchronous:
            item["async"] = True
        return [{"hooks": [item]}]

    return {
        "SessionStart": hook("session-start", 10),
        "UserPromptSubmit": hook("prompt-submit", 10),
        "PreToolUse": hook("pre-tool", 5),
        "PostToolUse": [{"hooks": [lifecycle]}],
        "PostToolUseFailure": [{"hooks": [lifecycle]}],
        "SubagentStart": [{"hooks": [lifecycle]}],
        "SubagentStop": [{"hooks": [lifecycle]}],
        "StopFailure": [{"hooks": [lifecycle]}],
        "Stop": hook("stop", 30, asynchronous=True),
        "SessionEnd": hook("session-end", 5),
    }


def _read_settings(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise click.ClickException(f"cannot read Claude settings: {path}") from error
    if not isinstance(value, dict):
        raise click.ClickException("Claude settings root must be an object")
    return value


def _is_managed_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks")
    if not isinstance(hooks, list):
        return False
    return any(
        isinstance(item, dict)
        and isinstance(item.get("command"), str)
        and "forecost.hooks.fastpath" in item["command"]
        for item in hooks
    )


def _without_managed(settings: dict[str, object]) -> dict[str, object]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings
    cleaned = {
        name: [entry for entry in entries if not _is_managed_entry(entry)]
        for name, entries in hooks.items()
        if isinstance(name, str) and isinstance(entries, list)
    }
    settings["hooks"] = {name: entries for name, entries in cleaned.items() if entries}
    return settings


def _install(settings: dict[str, object]) -> dict[str, object]:
    settings = _without_managed(settings)
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise click.ClickException("Claude settings hooks must be an object")
    for name, entries in _managed_hooks().items():
        existing = hooks.setdefault(name, [])
        if not isinstance(existing, list):
            raise click.ClickException(f"Claude hook {name} must be an array")
        existing.extend(entries)
    return settings


def _write_settings(path: Path, settings: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_suffix(path.suffix + ".forecost.bak")
    if path.is_file() and not backup.exists():
        shutil.copy2(path, backup)
        backup.chmod(0o600)
    descriptor, temporary_raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(settings, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _installed(settings: dict[str, object]) -> bool:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    expected = set(_managed_hooks())
    return expected.issubset(hooks) and all(
        isinstance(hooks[name], list) and any(_is_managed_entry(item) for item in hooks[name])
        for name in expected
    )


def _protocol_installed(settings_path: Path) -> bool:
    try:
        value = json.loads(_protocol_path(settings_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and value.get("hook_protocol_version") == HOOK_PROTOCOL_VERSION


@click.group()
def setup() -> None:
    """Prepare reversible local integrations."""


def _setup_mode(**modes: bool) -> str:
    selected = [name for name, enabled in modes.items() if enabled]
    if len(selected) != 1:
        raise click.UsageError(
            "choose exactly one of --dry-run/--check/--apply/--repair/--uninstall"
        )
    return selected[0]


def _validate_plugin(root: Path) -> None:
    required = (
        root / ".claude-plugin" / "plugin.json",
        root / "hooks" / "hooks.json",
        root / "scripts" / "run-hook.sh",
    )
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise click.ClickException(f"plugin package is incomplete: {', '.join(missing)}")


def _check(path: Path, settings: dict[str, object]) -> None:
    state = "installed" if _installed(settings) and _protocol_installed(path) else "not installed"
    click.echo(
        f"Claude plugin package: ready; managed config: {state}; protocol v{HOOK_PROTOCOL_VERSION}."
    )


def _dry_run(root: Path, path: Path) -> None:
    click.echo("Claude setup dry run (no files changed):")
    click.echo(f"  plugin root: {root}")
    click.echo(f"  settings: {path}")
    click.echo("  action: install/repair versioned Forecost hook entries only")


def _uninstall(path: Path, settings: dict[str, object]) -> None:
    _without_managed(settings)
    _write_settings(path, settings)
    _protocol_path(path).unlink(missing_ok=True)
    click.echo(f"Removed Forecost-managed Claude hooks from {path}.")


def _apply(path: Path, settings: dict[str, object], *, repair: bool) -> None:
    _write_settings(path, _install(settings))
    _write_settings(_protocol_path(path), {"hook_protocol_version": HOOK_PROTOCOL_VERSION})
    action = "Repaired" if repair else "Installed"
    click.echo(f"{action} Forecost-managed Claude hooks in {path}.")


@setup.command("claude")
@click.option("--dry-run", is_flag=True, help="Print the exact local installation plan.")
@click.option("--check", "check_only", is_flag=True, help="Validate package/config state.")
@click.option("--apply", "apply_changes", is_flag=True, help="Install managed hooks.")
@click.option("--repair", is_flag=True, help="Replace only Forecost-managed hook entries.")
@click.option("--uninstall", is_flag=True, help="Remove only Forecost-managed hook entries.")
@click.option("--config-dir", type=click.Path(path_type=Path), default=None)
@click.option("--plugin-root", type=click.Path(path_type=Path), default=None)
def setup_claude(
    dry_run: bool,
    check_only: bool,
    apply_changes: bool,
    repair: bool,
    uninstall: bool,
    config_dir: Path | None,
    plugin_root: Path | None,
) -> None:
    """Check, install, repair or remove Forecost's Claude hooks."""
    mode = _setup_mode(
        dry_run=dry_run,
        check=check_only,
        apply=apply_changes,
        repair=repair,
        uninstall=uninstall,
    )
    root = (plugin_root or _plugin_root()).resolve()
    _validate_plugin(root)
    path = _config_path(config_dir)
    settings = _read_settings(path)
    if mode == "check":
        _check(path, settings)
        return
    if mode == "dry_run":
        _dry_run(root, path)
        return
    if mode == "uninstall":
        _uninstall(path, settings)
        return
    _apply(path, settings, repair=mode == "repair")
