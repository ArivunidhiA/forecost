import os

import click
from rich.console import Console
from rich.table import Table

from llmcast.db import get_or_create_db, get_project_by_path

console = Console()

ALWAYS_SWITCH = {
    "gpt-4-turbo": ("gpt-4o", 0.67),
    "gpt-4": ("gpt-4o", 0.92),
    "claude-3-opus-20240229": ("claude-3-5-sonnet-latest", 0.80),
    "claude-3-opus-latest": ("claude-3-5-sonnet-latest", 0.80),
}

SHORT_OUTPUT_SWITCH = {
    "gpt-4o": ("gpt-4o-mini", 0.94),
    "claude-3-5-sonnet-20241022": ("claude-3-5-haiku-latest", 0.73),
    "claude-3-5-sonnet-latest": ("claude-3-5-haiku-latest", 0.73),
}


@click.command()
def optimize():
    """Suggest cost optimizations based on your usage."""
    project_path = os.path.abspath(os.getcwd())
    project = get_project_by_path(project_path)
    if project is None:
        console.print(
            f"[red]No llmcast project found in {project_path}[/red]\n\n"
            "  Run [bold]llmcast init[/bold] first."
        )
        raise SystemExit(1)

    conn = get_or_create_db()
    rows = conn.execute(
        "SELECT model, COUNT(*) AS calls, SUM(cost_usd) AS total_cost "
        "FROM usage_logs WHERE project_id = ? GROUP BY model",
        (project["id"],),
    ).fetchall()

    if not rows:
        console.print(
            "[yellow]No usage data yet.[/yellow]\n\n"
            "  Start tracking to get optimization suggestions:\n"
            "    import llmcast; llmcast.auto_track()"
        )
        return

    suggestions = []
    total_savings = 0.0

    for r in rows:
        model = r["model"]
        calls = r["calls"]
        cost = float(r["total_cost"])

        if model in ALWAYS_SWITCH:
            alt, savings_pct = ALWAYS_SWITCH[model]
            saved = cost * savings_pct
            total_savings += saved
            suggestions.append(
                {
                    "model": model,
                    "alternative": alt,
                    "reason": f"Newer/cheaper model ({calls} calls)",
                    "savings": saved,
                }
            )
        elif model in SHORT_OUTPUT_SWITCH:
            alt, savings_pct = SHORT_OUTPUT_SWITCH[model]
            short = conn.execute(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(cost_usd), 0) as cost "
                "FROM usage_logs "
                "WHERE project_id = ? AND model = ? AND tokens_out < 200",
                (project["id"], model),
            ).fetchone()
            short_count = short["cnt"]
            short_cost = float(short["cost"])
            if short_count > 0:
                saved = short_cost * savings_pct
                total_savings += saved
                suggestions.append(
                    {
                        "model": model,
                        "alternative": alt,
                        "reason": f"{short_count} of {calls} calls have short outputs",
                        "savings": saved,
                    }
                )

    if not suggestions:
        console.print("[green]Your model choices look efficient.[/green]")
        return

    table = Table(title="Optimization Suggestions")
    table.add_column("Current Model", style="cyan")
    table.add_column("Suggested", style="green")
    table.add_column("Reason")
    table.add_column("Potential Savings", justify="right", style="bold")
    for s in suggestions:
        table.add_row(s["model"], s["alternative"], s["reason"], f"${s['savings']:.2f}")

    console.print(table)
    console.print(f"\n[bold]Total potential savings: ${total_savings:.2f}[/bold]")
