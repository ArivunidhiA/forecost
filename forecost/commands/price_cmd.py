import json

import click
from rich.console import Console
from rich.table import Table

from forecost.pricing import FALLBACK_PRICING, get_provider, get_tier

console = Console()


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--tier", "filter_tier", default=None, help="Filter by tier (1, 2, or 3)")
def price(as_json, filter_tier):
    """Show LLM pricing for all supported models."""
    entries = []
    seen = set()
    for model, costs in FALLBACK_PRICING.items():
        base = model
        if base in seen:
            continue
        seen.add(base)
        provider = get_provider(model)
        tier = get_tier(model)
        tier_num = tier[5] if tier.startswith("Tier") else "?"
        entries.append(
            {
                "provider": provider,
                "model": model,
                "input_per_1m": costs["input"],
                "output_per_1m": costs["output"],
                "tier": tier,
                "tier_num": tier_num,
            }
        )

    if filter_tier:
        entries = [e for e in entries if e["tier_num"] == filter_tier]

    entries.sort(key=lambda e: (e["provider"], e["input_per_1m"]))

    if as_json:
        click.echo(json.dumps(entries, indent=2))
        return

    table = Table(title="LLM Pricing (per 1M tokens)")
    table.add_column("Provider", style="cyan")
    table.add_column("Model", style="bold")
    table.add_column("Input ($/1M)", justify="right", style="green")
    table.add_column("Output ($/1M)", justify="right", style="yellow")
    table.add_column("Tier", style="dim")

    for e in entries:
        table.add_row(
            e["provider"],
            e["model"],
            f"${e['input_per_1m']:.2f}",
            f"${e['output_per_1m']:.2f}",
            e["tier"],
        )

    console.print(table)
    console.print(f"\n[dim]{len(entries)} models listed[/dim]")
