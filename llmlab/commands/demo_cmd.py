import os
import tempfile
from datetime import datetime, timedelta, timezone

import click
from rich.console import Console

from llmlab.db import create_project, get_or_create_db, get_project_by_path
from llmlab.forecaster import ProjectForecaster
from llmlab.pricing import calculate_cost

console = Console()


@click.command()
def demo():
    """See llmlab in action with sample data."""
    demo_dir = os.path.join(tempfile.gettempdir(), "llmlab-demo")
    os.makedirs(demo_dir, exist_ok=True)

    existing = get_project_by_path(demo_dir)
    if existing:
        conn = get_or_create_db()
        conn.execute("DELETE FROM forecasts WHERE project_id = ?", (existing["id"],))
        conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (existing["id"],))
        conn.execute("DELETE FROM projects WHERE id = ?", (existing["id"],))
        conn.commit()

    pid = create_project(
        name="demo-project",
        path=demo_dir,
        baseline_daily_cost=0.50,
        baseline_total_days=14,
        baseline_total_cost=7.00,
    )

    conn = get_or_create_db()
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)

    # 10 days of realistic data showing model switching and cost patterns
    day_configs = [
        (1, "gpt-4o", 30, 1000, 500),  # Day 1-3: gpt-4o, moderate use
        (2, "gpt-4o", 35, 1200, 600),
        (3, "gpt-4o", 40, 1100, 550),
        (4, "gpt-4o", 50, 1500, 700),  # Day 4-6: ramping up
        (5, "gpt-4o", 55, 1400, 650),
        (6, "gpt-4o", 60, 1600, 800),
        (7, "gpt-4o-mini", 80, 800, 400),  # Day 7: switch to cheaper model
        (8, "gpt-4o-mini", 70, 900, 450),  # Day 8-10: mix
        (9, "gpt-4o", 20, 1200, 600),
        (10, "gpt-4o-mini", 60, 700, 350),
    ]

    for day_offset, model, num_calls, avg_in, avg_out in day_configs:
        ts = (base - timedelta(days=10 - day_offset)).isoformat()
        cost = num_calls * calculate_cost(model, avg_in, avg_out)
        conn.execute(
            "INSERT INTO usage_logs (project_id, timestamp, model, provider, "
            "tokens_in, tokens_out, cost_usd, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, ts, model, "openai", avg_in * num_calls, avg_out * num_calls, cost, None),
        )
    conn.commit()

    # Run forecaster and build 3 iterations to show convergence
    for i in range(3):
        f = ProjectForecaster(pid)
        result = f.calculate_forecast(save=True)

    # Display the final result
    console.print()
    # (reuse the same display logic as forecast_cmd but inline)
    from rich.panel import Panel
    from rich.table import Table

    summary = Table(show_header=False)
    summary.add_column("", style="dim")
    summary.add_column("")
    summary.add_row("Projected total", f"${result['projected_total']:.2f}")
    summary.add_row("Actual spend", f"${result['actual_spend']:.2f}")
    summary.add_row("Remaining", f"${result['projected_remaining']:.2f}")
    summary.add_row("Confidence", result["confidence"])
    summary.add_row("Drift", result["drift_status"].replace("_", " ").title())
    if result.get("stability") is not None:
        lbl = result.get("stability_label", "")
        summary.add_row("Stability", f"{result['stability']:.1f}% ({lbl})")

    model_table = Table(title="Model breakdown")
    model_table.add_column("Model", style="cyan")
    model_table.add_column("Spent", justify="right")
    model_table.add_column("Projected", justify="right")
    model_table.add_column("Share", justify="right")
    for m in result.get("model_breakdown", []):
        model_table.add_row(
            m["model"], f"${m['spent']:.2f}", f"${m['projected']:.2f}", f"{m['share']:.0%}"
        )

    console.print(
        Panel(summary, title="[bold]llmlab demo -- Cost Forecast[/bold]", border_style="blue")
    )
    if result.get("model_breakdown"):
        console.print(model_table)

    console.print()
    console.print("[dim]This is sample data. To track your real project:[/dim]")
    console.print("  cd your-project/")
    console.print("  llmlab init")
    console.print()

    # Clean up demo data from DB
    try:
        conn = get_or_create_db()
        conn.execute("DELETE FROM forecasts WHERE project_id = ?", (pid,))
        conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (pid,))
        conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
        conn.commit()
    except Exception:
        pass
