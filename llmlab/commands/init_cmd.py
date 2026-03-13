import os
from datetime import datetime, timezone

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from llmlab.db import create_project, get_project_by_path
from llmlab.scope import analyze_heuristic, analyze_with_llm

console = Console()


@click.command()
@click.option(
    "--smart", is_flag=True, help="Use LLM to analyze project scope (requires llmlab[llm])"
)
@click.option("--days", type=int, default=None, help="Override estimated project duration")
@click.option("--budget", type=float, default=None, help="Set a budget cap in USD")
def init(smart, days, budget):
    """Initialize llmlab for the current project."""
    project_path = os.path.abspath(os.getcwd())
    project_name = os.path.basename(project_path)

    existing = get_project_by_path(project_path)
    if existing:
        console.print(
            "[yellow]Project already initialized. Re-run with a different"
            " directory or remove .llmlab.toml.[/yellow]"
        )
        raise SystemExit(1)

    if smart:
        result = analyze_with_llm(project_path)
    else:
        result = analyze_heuristic(project_path)

    estimated_days = result["estimated_days"]
    if days is not None:
        estimated_days = days

    daily_cost = result["daily_cost"]
    total_cost = daily_cost * estimated_days

    metadata = {
        "project_type": result["project_type"],
        "model": result["model"],
        "confidence": result["confidence"],
        "calls_per_day": result["calls_per_day"],
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
    }
    if budget is not None:
        metadata["budget"] = budget

    try:
        create_project(
            name=project_name,
            path=project_path,
            baseline_daily_cost=daily_cost,
            baseline_total_days=estimated_days,
            baseline_total_cost=total_cost,
            metadata=metadata,
        )
    except Exception as e:
        console.print(f"[red]Failed to create project: {e}[/red]")
        raise SystemExit(1)

    config_path = os.path.join(project_path, ".llmlab.toml")
    created_at = datetime.now(timezone.utc).isoformat()
    config_content = f'''project_name = "{project_name}"
project_path = "{project_path}"
created_at = "{created_at}"
'''
    try:
        with open(config_path, "w") as f:
            f.write(config_content)
    except OSError as e:
        console.print(f"[yellow]Could not write .llmlab.toml: {e}[/yellow]")

    table = Table(show_header=False)
    table.add_column("", style="dim")
    table.add_column("")
    table.add_row("Project", project_name)
    table.add_row("Type", result["project_type"])
    table.add_row("Model", result["model"])
    table.add_row("Duration", f"{estimated_days} days")
    table.add_row("Daily cost", f"${daily_cost:.2f}")
    table.add_row("Total projected", f"${total_cost:.2f}")
    table.add_row("Confidence", result["confidence"])

    if budget is not None:
        status = "Under budget" if total_cost <= budget else "Over budget"
        table.add_row("Budget", f"${budget:.2f} ({status})")

    content = table
    console.print(Panel(content, title="[bold]llmlab initialized[/bold]", border_style="green"))
