import shutil
from pathlib import Path

import click
from rich.console import Console

from forecost.core.paths import forecost_home

console = Console()


def _collect_and_delete(keep_config: bool) -> list[str]:
    """Delete forecost data, returning the paths actually removed."""
    removed: list[str] = []
    home = forecost_home()  # honors FORECOST_HOME, not a hardcoded ~/.forecost
    if home.exists():
        shutil.rmtree(home)
        removed.append(str(home))
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
    console.print(
        "\n[green]Purge complete.[/green] Run [bold]forecost ingest[/bold] to start fresh."
    )


def _confirm_prompt() -> str:
    return (
        f"This deletes ALL forecost data at {forecost_home()} — including "
        "ledger.db (your entire spend + calibration history, which cannot be "
        "recovered), costs.db, error.log, and recovery.jsonl. Continue?"
    )


@click.command()
@click.option("--keep-config", is_flag=True, help="Keep .forecost.toml in the current directory")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
def purge(keep_config: bool, yes: bool) -> None:
    """Remove all forecost data from this machine.

    Deletes the forecost home directory ($FORECOST_HOME or ~/.forecost),
    including ledger.db — your irreplaceable spend and calibration history —
    plus the legacy costs.db, error.log, and recovery.jsonl, and optionally the
    .forecost.toml config in the current directory.
    """
    if not yes and not click.confirm(_confirm_prompt()):
        console.print("[yellow]Aborted.[/yellow] Nothing was deleted.")
        return
    _report(_collect_and_delete(keep_config))
