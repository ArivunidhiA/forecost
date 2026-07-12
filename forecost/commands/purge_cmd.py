import shutil
from pathlib import Path

import click
from rich.console import Console

console = Console()

_FORECOST_DIR = Path.home() / ".forecost"


def _collect_and_delete(keep_config: bool) -> list[str]:
    """Delete forecost data, returning the paths actually removed."""
    removed: list[str] = []
    if _FORECOST_DIR.exists():
        shutil.rmtree(_FORECOST_DIR)
        removed.append(str(_FORECOST_DIR))
    if not keep_config:
        local_toml = Path.cwd() / ".forecost.toml"
        if local_toml.exists():
            local_toml.unlink()
            removed.append(str(local_toml))
    return removed


def _report(removed: list[str]) -> None:
    if not removed:
        console.print("[yellow]Nothing to purge.[/yellow] No forecost data found.")
        return
    for path in removed:
        console.print(f"  [red]Deleted[/red] {path}")
    console.print("\n[green]Purge complete.[/green] Run [bold]forecost init[/bold] to start fresh.")


@click.command()
@click.option("--keep-config", is_flag=True, help="Keep .forecost.toml in the current directory")
@click.confirmation_option(prompt="This will delete ALL forecost data (~/.forecost/). Continue?")
def purge(keep_config: bool) -> None:
    """Remove all forecost data from this machine.

    Deletes ~/.forecost/ (costs.db, error.log, recovery.jsonl) and optionally
    the .forecost.toml config in the current directory.
    """
    _report(_collect_and_delete(keep_config))
