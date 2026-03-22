import os

import click
from rich.console import Console
from rich.table import Table

from forecost.db import get_or_create_db, get_project_by_path
from forecost.pricing import FALLBACK_PRICING, MODEL_TIERS, get_provider, get_tier

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


def _classify_task(avg_in: float, avg_out: float) -> str:
    if avg_in > 20000 or avg_out > 800:
        return "Heavy"
    if avg_in < 5000 and avg_out < 200:
        return "Light"
    return "Standard"


def _get_tier_models(tier_name: str) -> list[str]:
    return MODEL_TIERS.get(tier_name, [])


def _find_cheaper_in_tier(model: str, tier_name: str) -> str | None:
    """Find a cheaper alternative within the same tier."""
    current_cost = FALLBACK_PRICING.get(model, {}).get("output", float("inf"))
    tier_models = _get_tier_models(tier_name)
    candidates = []
    for m in tier_models:
        if m == model:
            continue
        pricing = FALLBACK_PRICING.get(m)
        if pricing and pricing["output"] < current_cost:
            candidates.append((m, pricing["output"]))
    if candidates:
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]
    return None


def _calc_savings_pct(model: str, alt: str) -> float:
    alt_out = FALLBACK_PRICING.get(alt, {}).get("output", 0)
    cur_out = FALLBACK_PRICING.get(model, {}).get("output", 0)
    if cur_out > 0:
        return 1 - (alt_out / cur_out)
    return 0.0


@click.command()
def optimize():
    """Suggest cost optimizations based on your usage."""
    project_path = os.path.abspath(os.getcwd())
    project = get_project_by_path(project_path)
    if project is None:
        console.print(
            f"[red]No forecost project found in {project_path}[/red]\n\n"
            "  Run [bold]forecost init[/bold] first."
        )
        raise SystemExit(1)

    conn = get_or_create_db()
    rows = conn.execute(
        "SELECT model, COUNT(*) AS calls, SUM(cost_usd) AS total_cost, "
        "AVG(tokens_in) AS avg_in, AVG(tokens_out) AS avg_out "
        "FROM usage_logs WHERE project_id = ? GROUP BY model",
        (project["id"],),
    ).fetchall()

    if not rows:
        console.print(
            "[yellow]No usage data yet.[/yellow]\n\n"
            "  Start tracking to get optimization suggestions:\n"
            "    import forecost; forecost.auto_track()"
        )
        return

    suggestions = []
    total_savings = 0.0

    for r in rows:
        model = r["model"]
        calls = r["calls"]
        cost = float(r["total_cost"])
        avg_in = float(r["avg_in"] or 0)
        avg_out = float(r["avg_out"] or 0)
        task_type = _classify_task(avg_in, avg_out)
        tier = get_tier(model)

        if model in ALWAYS_SWITCH:
            alt, savings_pct = ALWAYS_SWITCH[model]
            saved = cost * savings_pct
            total_savings += saved
            suggestions.append(
                {
                    "model": model,
                    "alternative": alt,
                    "task": task_type,
                    "reason": f"Newer/cheaper model ({calls} calls)",
                    "savings": saved,
                }
            )
        elif task_type == "Light" and tier == "Tier 1 (Heavy)":
            tier2_models = _get_tier_models("Tier 2 (Standard)")
            provider = get_provider(model)
            alt = next((t2 for t2 in tier2_models if get_provider(t2) == provider), None)
            if alt:
                savings_pct = _calc_savings_pct(model, alt)
                saved = cost * max(0, savings_pct)
                total_savings += saved
                suggestions.append(
                    {
                        "model": model,
                        "alternative": alt,
                        "task": task_type,
                        "reason": f"Short outputs (avg {avg_out:.0f} tok) safe for Tier 2",
                        "savings": saved,
                    }
                )
        elif task_type == "Heavy" and tier == "Tier 1 (Heavy)":
            alt = _find_cheaper_in_tier(model, tier)
            if alt:
                savings_pct = _calc_savings_pct(model, alt)
                if savings_pct > 0.1:
                    saved = cost * savings_pct
                    total_savings += saved
                    suggestions.append(
                        {
                            "model": model,
                            "alternative": alt,
                            "task": task_type,
                            "reason": f"Lateral Tier 1 move ({calls} heavy calls)",
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
                        "task": task_type,
                        "reason": f"{short_count}/{calls} calls have short outputs",
                        "savings": saved,
                    }
                )

    if not suggestions:
        console.print("[green]Your model choices look efficient.[/green]")
        return

    table = Table(title="Optimization Suggestions")
    table.add_column("Current Model", style="cyan")
    table.add_column("Suggested", style="green")
    table.add_column("Task Profile", style="dim")
    table.add_column("Reason")
    table.add_column("Potential Savings", justify="right", style="bold")
    for s in suggestions:
        table.add_row(
            s["model"],
            s["alternative"],
            s.get("task", ""),
            s["reason"],
            f"${s['savings']:.2f}",
        )

    console.print(table)
    console.print(f"\n[bold]Total potential savings: ${total_savings:.2f}[/bold]")
