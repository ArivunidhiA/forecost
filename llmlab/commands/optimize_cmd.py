import os

import click
from rich.console import Console
from rich.table import Table

from llmlab.db import get_or_create_db, get_project_by_path

console = Console()

CHEAPER_ALTERNATIVES = {
    "gpt-4o": ("gpt-4o-mini", 0.94),
    "gpt-4-turbo": ("gpt-4o", 0.67),
    "gpt-4": ("gpt-4o", 0.92),
    "claude-3-opus-20240229": ("claude-3-5-sonnet-latest", 0.80),
    "claude-3-opus-latest": ("claude-3-5-sonnet-latest", 0.80),
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
            f"[red]No llmlab project found in {project_path}[/red]\n\n"
            "  Run [bold]llmlab init[/bold] first."
        )
        raise SystemExit(1)

    conn = get_or_create_db()
    rows = conn.execute(
        "SELECT model, COUNT(*) AS calls, "
        "AVG(tokens_out) AS avg_out, SUM(cost_usd) AS total_cost "
        "FROM usage_logs WHERE project_id = ? GROUP BY model",
        (project["id"],),
    ).fetchall()

    if not rows:
        console.print(
            "[yellow]No usage data yet.[/yellow]\n\n"
            "  Start tracking to get optimization suggestions:\n"
            "    import llmlab; llmlab.auto_track()"
        )
        return

    suggestions = []
    total_savings = 0.0

    for r in rows:
        model = r["model"]
        calls = r["calls"]
        avg_out = float(r["avg_out"] or 0)
        cost = float(r["total_cost"])

        if model in CHEAPER_ALTERNATIVES:
            alt, savings_pct = CHEAPER_ALTERNATIVES[model]
            if avg_out < 200:
                saved = cost * savings_pct
                total_savings += saved
                suggestions.append(
                    {
                        "model": model,
                        "alternative": alt,
                        "reason": f"Short outputs (avg {avg_out:.0f} tokens)",
                        "savings": saved,
                        "calls": calls,
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
