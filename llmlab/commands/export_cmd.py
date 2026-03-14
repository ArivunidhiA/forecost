import csv
import json
import os
import sys

import click
from rich.console import Console

from llmlab.db import get_project_by_path, get_recent_usage_logs

console = Console()


@click.command(name="export")
@click.option(
    "--format", "fmt", type=click.Choice(["csv", "json"]), default="csv", help="Output format"
)
@click.option("--limit", type=int, default=1000, help="Maximum rows to export")
def export_data(fmt, limit):
    """Export usage data as CSV or JSON."""
    project_path = os.path.abspath(os.getcwd())
    project = get_project_by_path(project_path)
    if project is None:
        console.print(
            f"[red]No llmlab project found in {project_path}[/red]\n\n"
            "  Run [bold]llmlab init[/bold] first."
        )
        raise SystemExit(1)

    logs = get_recent_usage_logs(project["id"], limit=limit)
    if not logs:
        console.print("[yellow]No usage data to export.[/yellow]")
        return

    if fmt == "json":
        print(json.dumps(logs, indent=2))
    else:
        writer = csv.writer(sys.stdout)
        writer.writerow(["timestamp", "model", "provider", "tokens_in", "tokens_out", "cost_usd"])
        for r in logs:
            writer.writerow(
                [
                    r.get("timestamp", ""),
                    r.get("model", ""),
                    r.get("provider", ""),
                    r.get("tokens_in", 0),
                    r.get("tokens_out", 0),
                    r.get("cost_usd", 0),
                ]
            )
