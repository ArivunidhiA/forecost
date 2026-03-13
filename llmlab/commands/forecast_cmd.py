import json
import os

import click
from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from llmlab.db import get_forecast_history, get_project_by_path
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


def _check_budget_exit(project: dict, result: dict) -> None:
    """Exit with CI-friendly code based on budget. Never returns."""
    budget = (project.get("metadata") or {}).get("budget")
    if budget is None:
        console.print("[dim]No budget set. Use llmlab init --budget X to set one.[/dim]")
        raise SystemExit(0)
    actual = result["actual_spend"]
    projected = result["projected_total"]
    if actual > budget:
        raise SystemExit(2)
    if projected > budget:
        raise SystemExit(1)
    raise SystemExit(0)


def _confidence_dots(confidence: str) -> str:
    levels = ["low", "medium-low", "medium", "high", "very-high"]
    idx = levels.index(confidence) if confidence in levels else 0
    filled = "\u25cf" * (idx + 1)
    empty = "\u25cb" * (5 - idx - 1)
    return filled + empty


def _build_premium_output(result: dict, project: dict) -> None:
    spent = result["actual_spend"]
    proj = result["projected_total"]
    remaining = result["projected_remaining"]
    pct = (spent / proj * 100) if proj > 0 else 0
    bar_len = 20
    filled_len = int(bar_len * pct / 100) if proj > 0 else 0
    bar = "\u2588" * filled_len + "\u2591" * (bar_len - filled_len)

    day = result["active_days"]
    total = result["total_days"]
    burn = result.get("smoothed_burn_ratio", 1.0)
    drift = _format_drift(result["drift_status"])
    conf_dots = _confidence_dots(result.get("confidence", "low"))

    stats_cols = Columns(
        [
            Text.from_markup(f"[dim]Day {day} of {total}[/dim]"),
            Text.from_markup(f"[dim]Confidence[/dim] {conf_dots}"),
            Text.from_markup(f"[dim]Burn rate[/dim] {burn:.2f}x"),
            drift,
        ],
        expand=True,
    )

    panel_content = Text()
    panel_content.append("Projected Total Cost  ", style="bold")
    panel_content.append(f"${proj:.2f}\n\n", style="bold cyan")
    panel_content.append(f"Spent ${spent:.2f}  ", style="dim")
    panel_content.append(bar, style="cyan")
    panel_content.append(f"  {pct:.0f}%\n", style="dim")
    panel_content.append(f"Remaining ${remaining:.2f}\n\n", style="dim")

    console.print(
        Panel(
            Group(panel_content, stats_cols),
            title="[bold]Cost forecast[/bold]",
            border_style="blue",
        )
    )

    model_table = Table(title="Model breakdown")
    model_table.add_column("Model", style="cyan")
    model_table.add_column("Spent", justify="right")
    model_table.add_column("Projected", justify="right")
    model_table.add_column("Share", justify="right")
    for m in result.get("model_breakdown", []):
        share_pct = (m.get("share", 0) or 0) * 100
        model_table.add_row(
            m["model"],
            f"${m['spent']:.2f}",
            f"${m['projected']:.2f}",
            f"{share_pct:.1f}%",
        )
    if result.get("model_breakdown"):
        console.print(model_table)

    history = get_forecast_history(project["id"])
    if len(history) >= 2:
        recent = history[-5:]
        totals = [h["projected_total"] for h in recent]
        mx = max(totals) if totals else 1
        bar_width = 16
        conv_table = Table(title="Forecast convergence")
        conv_table.add_column("Run", justify="right", style="dim")
        conv_table.add_column("Projected", justify="right")
        conv_table.add_column("", style="cyan")
        for i, h in enumerate(recent):
            val = h["projected_total"]
            bar_len_i = int((val / mx) * bar_width) if mx > 0 else 0
            bar_str = "\u2588" * bar_len_i + "\u2591" * (bar_width - bar_len_i)
            conv_table.add_row(str(h["iteration"]), f"${val:.2f}", bar_str)
        console.print(conv_table)

    if result.get("stability") is not None:
        label = result.get("stability_label", "")
        console.print(f"[dim]Stability: {result['stability']:.1f}% avg change ({label})[/dim]")


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--tui", is_flag=True, help="Launch interactive TUI dashboard")
@click.option("--brief", is_flag=True, help="One-line summary")
@click.option("--exit-code", is_flag=True, help="Exit 1 if over budget (for CI)")
def forecast(as_json, tui, brief, exit_code):
    """Run cost forecast for the current project."""
    project_path = os.path.abspath(os.getcwd())
    project = get_project_by_path(project_path)

    if project is None:
        console.print(
            f"[red]No llmlab project found in {project_path}[/red]\n\n"
            "  To get started:\n"
            f"    cd {project_path}\n"
            "    llmlab init\n\n"
            "  llmlab looks for a .llmlab.toml file in the current directory."
        )
        raise SystemExit(1)

    try:
        forecaster = ProjectForecaster(project["id"])
        result = forecaster.calculate_forecast(save=True)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    if as_json:
        print(json.dumps(result, indent=2))
        if exit_code:
            _check_budget_exit(project, result)
        return

    if tui:
        from llmlab.tui import launch

        def on_refresh():
            return ProjectForecaster(project["id"]).calculate_forecast()

        launch(result, project["id"], on_refresh=on_refresh)
        if exit_code:
            _check_budget_exit(project, result)
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
        if exit_code:
            _check_budget_exit(project, result)
        return

    _build_premium_output(result, project)
    if result["active_days"] == 0:
        console.print(
            "[dim]No usage data yet. Forecast is based on the initial estimate.\n"
            "  To start tracking: add 'import llmlab; llmlab.auto_track()' to your app.[/dim]"
        )
    if exit_code:
        _check_budget_exit(project, result)
