"""Safe, non-mutating Claude plugin setup guidance and local checks."""

from __future__ import annotations

from pathlib import Path

import click


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[2] / "plugin"


@click.group()
def setup() -> None:
    """Prepare integrations without silently modifying host-agent settings."""


@setup.command("claude")
@click.option("--dry-run", is_flag=True, help="Print the exact local installation plan.")
@click.option("--check", "check_only", is_flag=True, help="Validate the bundled plugin shape only.")
@click.option("--plugin-root", type=click.Path(path_type=Path), default=None)
def setup_claude(dry_run: bool, check_only: bool, plugin_root: Path | None) -> None:
    """Inspect the local Claude plugin; it never edits Claude configuration itself."""
    if dry_run and check_only:
        raise click.UsageError("choose either --dry-run or --check")
    root = (plugin_root or _plugin_root()).resolve()
    manifest = root / ".claude-plugin" / "plugin.json"
    hooks = root / "hooks" / "hooks.json"
    launcher = root / "scripts" / "run-hook.sh"
    missing = [path.name for path in (manifest, hooks, launcher) if not path.is_file()]
    if missing:
        raise click.ClickException(f"plugin package is incomplete: {', '.join(missing)}")
    if check_only:
        click.echo("Claude plugin package: ready for manual installation (no host config changed).")
        return
    if not dry_run:
        raise click.UsageError("setup is intentionally non-mutating; use --dry-run or --check")
    click.echo("Claude setup dry run (no files changed):")
    click.echo(f"  plugin root: {root}")
    click.echo("  install through Claude Code's plugin UI or marketplace command")
    click.echo("  for this local root")
    click.echo("  then run: forecost self-test claude")
