import os
import time

import click
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from llmlab.db import get_daily_costs, get_project_by_path, get_recent_usage_logs

console = Console()


def _build_display(project):
    pid = project["id"]
    daily_costs = get_daily_costs(pid)
    total = sum(c for _, c in daily_costs)
    logs = get_recent_usage_logs(pid, limit=5)
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("", style="dim")
    table.add_column("")
    table.add_row("Total", f"[bold green]${total:.4f}[/bold green]")
    table.add_row("Calls", str(len(daily_costs)))
    table.add_row("", "")

    if logs:
        log_table = Table(title="Recent calls", box=None)
        log_table.add_column("Time", style="dim")
        log_table.add_column("Model", style="cyan")
        log_table.add_column("Tokens", justify="right")
        log_table.add_column("Cost", justify="right", style="green")
        for r in logs:
            ts = r.get("timestamp", "")[:19].replace("T", " ")
            tok = r.get("tokens_in", 0) + r.get("tokens_out", 0)
            log_table.add_row(ts, r.get("model", "?"), f"{tok:,}", f"${r.get('cost_usd', 0):.4f}")
        return table, log_table
    return table, Text("No calls yet", style="dim")


@click.command()
@click.option("--interval", default=5, help="Refresh interval in seconds")
def watch(interval):
    """Live cost dashboard. Updates as your app makes LLM calls."""
    project_path = os.path.abspath(os.getcwd())
    project = get_project_by_path(project_path)
    if project is None:
        console.print(
            f"[red]No llmlab project found in {project_path}[/red]\n\n"
            "  Run [bold]llmlab init[/bold] first."
        )
        raise SystemExit(1)

    console.print("[bold]llmlab watch[/bold] — Live Cost Dashboard (Ctrl+C to stop)\n")
    try:
        with Live(console=console, refresh_per_second=1) as live:
            while True:
                summary, details = _build_display(project)
                live.update(Columns([summary, details], padding=(0, 4)))
                time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
