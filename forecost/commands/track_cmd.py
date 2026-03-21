import os

import click
from rich.console import Console
from rich.table import Table

from forecost.db import get_project_by_path, get_recent_usage_logs

console = Console()


@click.command()
@click.option("--limit", default=20, help="Number of recent calls to show")
def track(limit):
    """View recent tracked LLM calls."""
    project_path = os.path.abspath(os.getcwd())
    project = get_project_by_path(project_path)

    if project is None:
        console.print(
            f"[red]No forecost project found in {project_path}[/red]\n\n"
            "  To get started:\n"
            f"    cd {project_path}\n"
            "    forecost init\n\n"
            "  forecost looks for a .forecost.toml file in the current directory."
        )
        raise SystemExit(1)

    logs = get_recent_usage_logs(project["id"], limit=limit)

    if not logs:
        console.print(
            "[yellow]No tracked calls yet.[/yellow]\n\n"
            "  Quick start:\n"
            "    import forecost\n"
            "    forecost.auto_track()  # Add to your app\n\n"
            "  Or track manually:\n"
            "    forecost.log_call(model='gpt-4o', tokens_in=500, tokens_out=200)"
        )
        return

    table = Table(title="Recent LLM calls")
    table.add_column("Time", style="dim")
    table.add_column("Model", style="cyan")
    table.add_column("Provider", style="magenta")
    table.add_column("Tokens In", justify="right")
    table.add_column("Tokens Out", justify="right")
    table.add_column("Cost", justify="right", style="green")

    for log in logs:
        ts = log["timestamp"][:19] if log.get("timestamp") else ""
        table.add_row(
            ts,
            log.get("model", ""),
            log.get("provider", ""),
            str(log.get("tokens_in", 0)),
            str(log.get("tokens_out", 0)),
            f"${log.get('cost_usd', 0):.4f}",
        )

    console.print(table)
