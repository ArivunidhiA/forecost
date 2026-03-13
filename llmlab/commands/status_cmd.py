import os

import click
from rich.console import Console

from llmlab.db import get_project_by_path
from llmlab.forecaster import ProjectForecaster

console = Console()


def _format_drift(status: str) -> str:
    if status == "on_track":
        return "On Track"
    if status == "over_budget":
        return "Over Budget"
    if status == "under_budget":
        return "Under Budget"
    return status


@click.command()
def status():
    """Show current project status."""
    project_path = os.path.abspath(os.getcwd())
    project = get_project_by_path(project_path)

    if project is None:
        console.print("[yellow]No llmlab project found. Run 'llmlab init' first.[/yellow]")
        raise SystemExit(1)

    try:
        forecaster = ProjectForecaster(project["id"])
        result = forecaster.calculate_forecast()
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    spent = result["actual_spend"]
    proj = result["projected_total"]
    day = result["active_days"]
    total = result["total_days"]
    drift = _format_drift(result["drift_status"])
    console.print(
        f"{result['project_name']} | ${spent:.2f} spent | ${proj:.2f} projected | "
        f"Day {day}/{total} | {drift}"
    )
