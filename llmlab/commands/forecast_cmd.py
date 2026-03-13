import json
import os

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from llmlab.db import get_project_by_path
from llmlab.forecaster import ProjectForecaster

console = Console()


def _format_drift(status: str) -> Text:
    if status == "on_track":
        return Text("On Track", style="green")
    if status == "over_budget":
        return Text("Over Budget", style="red bold")
    if status == "under_budget":
        return Text("Under Budget", style="yellow")
    return Text(status, style="dim")


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--tui", is_flag=True, help="Launch interactive TUI dashboard")
@click.option("--brief", is_flag=True, help="One-line summary")
def forecast(as_json, tui, brief):
    """Run cost forecast for the current project."""
    project_path = os.path.abspath(os.getcwd())
    project = get_project_by_path(project_path)

    if project is None:
        console.print("[red]No llmlab project found. Run 'llmlab init' first.[/red]")
        raise SystemExit(1)

    try:
        forecaster = ProjectForecaster(project["id"])
        result = forecaster.calculate_forecast()
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    if tui:
        from llmlab.tui import launch

        def on_refresh():
            return ProjectForecaster(project["id"]).calculate_forecast()

        launch(result, project["id"], on_refresh=on_refresh)
        return

    if brief:
        spent = result["actual_spend"]
        proj = result["projected_total"]
        day = result["active_days"]
        total = result["total_days"]
        drift = _format_drift(result["drift_status"])
        console.print(
            f"{result['project_name']} | ${spent:.2f} spent | ${proj:.2f} projected | "
            f"Day {day}/{total} | {drift}"
        )
        return

    summary = Table(show_header=False)
    summary.add_column("", style="dim")
    summary.add_column("")
    summary.add_row("Projected total", f"${result['projected_total']:.2f}")
    summary.add_row("Actual spend", f"${result['actual_spend']:.2f}")
    summary.add_row("Projected remaining", f"${result['projected_remaining']:.2f}")
    summary.add_row("Drift", _format_drift(result["drift_status"]))
    summary.add_row("Confidence", result["confidence"])
    if result.get("mape") is not None:
        summary.add_row("MAPE accuracy", f"{result['mape']:.1f}%")

    model_table = Table(title="Model breakdown")
    model_table.add_column("Model", style="cyan")
    model_table.add_column("Spent", justify="right")
    model_table.add_column("Projected", justify="right")
    for m in result.get("model_breakdown", []):
        model_table.add_row(
            m["model"],
            f"${m['spent']:.2f}",
            f"${m['projected']:.2f}",
        )

    console.print(Panel(summary, title="[bold]Cost forecast[/bold]", border_style="blue"))
    if result.get("model_breakdown"):
        console.print(model_table)
