import os

import click
from rich.console import Console

from forecost.db import get_project_by_path
from forecost.forecaster import ProjectForecaster

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
        console.print(
            f"[red]No forecost project found in {project_path}[/red]\n\n"
            "  To get started:\n"
            f"    cd {project_path}\n"
            "    forecost init\n\n"
            "  forecost looks for a .forecost.toml file in the current directory."
        )
        raise SystemExit(1)

    try:
        forecaster = ProjectForecaster(project["id"])
        result = forecaster.calculate_forecast(save=False)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    spent = result["actual_spend"]
    proj = result["projected_total"]
    day = result["active_days"]
    total = result["total_days"]
    drift = _format_drift(result["drift_status"])
    tokens = result.get("total_tokens", 0)
    name = result["project_name"]
    console.print(
        f"{name} | {tokens:,} tokens | ${spent:.2f} spent | "
        f"${proj:.2f} projected | Day {day}/{total} | {drift}"
    )
