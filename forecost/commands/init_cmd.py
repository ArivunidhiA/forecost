import os
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forecost.db import create_project, get_or_create_db, get_project_by_path
from forecost.scope import analyze_heuristic, analyze_with_llm

console = Console()


def _remove_existing_project_data(existing: dict, project_path: str) -> None:
    conn = get_or_create_db()
    pid = existing["id"]
    conn.execute("DELETE FROM forecasts WHERE project_id = ?", (pid,))
    conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (pid,))
    conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
    conn.commit()
    toml_path = Path(project_path) / ".forecost.toml"
    if toml_path.exists():
        toml_path.unlink()


def _build_metadata(result: dict, budget: float | None) -> dict:
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
    return metadata


def _write_project_config(project_path: str, project_name: str) -> None:
    config_path = Path(project_path) / ".forecost.toml"
    created_at = datetime.now(timezone.utc).isoformat()
    safe_name = project_name.replace("\\", "\\\\").replace('"', '\\"')
    config_content = f'''project_name = "{safe_name}"
path = "."
created_at = "{created_at}"
'''

    try:
        config_path.write_text(config_content, encoding="utf-8")
    except OSError as e:
        console.print(f"[yellow]Could not write .forecost.toml: {e}[/yellow]")
        return

    gitignore_path = Path(project_path) / ".gitignore"
    if gitignore_path.is_file():
        gitignore_content = gitignore_path.read_text(encoding="utf-8")
        if ".forecost.toml" not in gitignore_content:
            console.print("[dim]Tip: Add .forecost.toml to your .gitignore[/dim]")


def _print_init_summary(
    *,
    project_name: str,
    result: dict,
    estimated_days: int,
    daily_cost: float,
    total_cost: float,
    budget: float | None,
) -> None:
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

    console.print(Panel(table, title="[bold]forecost initialized[/bold]", border_style="green"))
    if result["project_type"] == "default":
        console.print(
            "[dim]Using default estimates. Override with: forecost init --days 14 --budget 50[/dim]"
        )


@click.command()
@click.option(
    "--smart",
    is_flag=True,
    help="Use an LLM to analyze project scope (requires forecost[llm]). "
    "OUTBOUND: sends project excerpts (README, code snippets) to an LLM provider.",
)
@click.option("--days", type=int, default=None, help="Override estimated project duration")
@click.option("--budget", type=float, default=None, help="Set a budget cap in USD")
def init(smart, days, budget):
    """Initialize forecost for the current project."""
    project_path = os.path.abspath(os.getcwd())
    project_name = os.path.basename(project_path)

    existing = get_project_by_path(project_path)
    if existing:
        if not click.confirm("Re-initialize?"):
            console.print(
                f"[yellow]Project already initialized at {project_path}[/yellow]\n\n"
                "  To reset: delete .forecost.toml and run forecost init again\n"
                "  Your usage history in ~/.forecost/costs.db is preserved."
            )
            raise SystemExit(1)
        _remove_existing_project_data(existing, project_path)

    if smart:
        console.print(
            "[yellow]--smart sends project excerpts (README, code snippets) to an LLM "
            "provider to estimate scope. This is the one forecost path that leaves your "
            "machine.[/yellow]"
        )
        if not click.confirm("Send project excerpts to the configured LLM provider?"):
            console.print("[dim]Falling back to local heuristic analysis.[/dim]")
            result = analyze_heuristic(project_path)
        else:
            result = analyze_with_llm(project_path)
    else:
        result = analyze_heuristic(project_path)

    estimated_days = result["estimated_days"]
    if days is not None:
        estimated_days = days

    daily_cost = result["daily_cost"]
    total_cost = daily_cost * estimated_days

    metadata = _build_metadata(result, budget)

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

    _write_project_config(project_path, project_name)
    _print_init_summary(
        project_name=project_name,
        result=result,
        estimated_days=estimated_days,
        daily_cost=daily_cost,
        total_cost=total_cost,
        budget=budget,
    )
