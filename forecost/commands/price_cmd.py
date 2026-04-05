import json

import click
from rich.console import Console
from rich.table import Table

from forecost.pricing import FALLBACK_PRICING, get_provider, get_tier

console = Console()


def _pricing_entries(filter_tier: str | None) -> list[dict]:
    entries: list[dict] = []
    seen: set[str] = set()
    for model, costs in FALLBACK_PRICING.items():
        if model in seen:
            continue
        seen.add(model)
        tier = get_tier(model)
        tier_num = tier[5] if tier.startswith("Tier") else "?"
        entries.append(
            {
                "provider": get_provider(model),
                "model": model,
                "input_per_1m": costs["input"],
                "output_per_1m": costs["output"],
                "tier": tier,
                "tier_num": tier_num,
            }
        )

    if filter_tier:
        entries = [entry for entry in entries if entry["tier_num"] == filter_tier]
    entries.sort(key=lambda entry: (entry["provider"], entry["input_per_1m"]))
    return entries


def _print_entries_table(entries: list[dict]) -> None:
    table = Table(title="LLM Pricing (per 1M tokens)")
    table.add_column("Provider", style="cyan")
    table.add_column("Model", style="bold")
    table.add_column("Input ($/1M)", justify="right", style="green")
    table.add_column("Output ($/1M)", justify="right", style="yellow")
    table.add_column("Tier", style="dim")

    for entry in entries:
        table.add_row(
            entry["provider"],
            entry["model"],
            f"${entry['input_per_1m']:.2f}",
            f"${entry['output_per_1m']:.2f}",
            entry["tier"],
        )

    console.print(table)
    console.print(f"\n[dim]{len(entries)} models listed[/dim]")


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--tier", "filter_tier", default=None, help="Filter by tier (1, 2, or 3)")
def price(as_json, filter_tier):
    """Show LLM pricing for all supported models."""
    entries = _pricing_entries(filter_tier)

    if as_json:
        click.echo(json.dumps(entries, indent=2))
        return
    _print_entries_table(entries)
