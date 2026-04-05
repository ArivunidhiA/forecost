import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from forecost.pricing import calculate_cost, get_tier

console = Console()


def _read_prompt(prompt: str | None, prompt_file: str | None) -> str | None:
    if not prompt_file:
        return prompt
    return Path(prompt_file).read_text(encoding="utf-8")


def _build_results(
    model_list: list[str], input_tokens: int, output_tokens: int, calls: int
) -> list[dict[str, float | int | str]]:
    results: list[dict[str, float | int | str]] = []
    for model in model_list:
        cost_per_call = calculate_cost(model, input_tokens, output_tokens)
        results.append(
            {
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_per_call": cost_per_call,
                "cost_total": cost_per_call * calls,
                "tier": get_tier(model),
            }
        )
    return results


def _print_json_output(
    *,
    input_tokens: int,
    output_tokens: int,
    calls: int,
    results: list[dict[str, float | int | str]],
) -> None:
    payload = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "calls": calls,
        "models": results,
    }
    click.echo(json.dumps(payload, indent=2))


def _print_table_output(
    *,
    input_tokens: int,
    output_tokens: int,
    calls: int,
    results: list[dict[str, float | int | str]],
) -> None:
    console.print(
        f"\n[dim]Input tokens:[/dim] [bold]{input_tokens:,}[/bold]  "
        f"[dim]Output tokens:[/dim] [bold]{output_tokens:,}[/bold]  "
        f"[dim]Calls:[/dim] [bold]{calls:,}[/bold]\n"
    )

    table = Table(title="Cost Comparison")
    table.add_column("Model", style="cyan")
    table.add_column("Tier", style="dim")
    table.add_column("Tokens (In/Out)", justify="right")
    table.add_column("Cost per call", justify="right", style="green")
    if calls > 1:
        table.add_column(f"Cost x{calls:,}", justify="right", style="bold yellow")

    for r in results:
        row = [
            str(r["model"]),
            str(r["tier"]),
            f"{int(r['input_tokens']):,} / {int(r['output_tokens']):,}",
            f"${float(r['cost_per_call']):.6f}",
        ]
        if calls > 1:
            row.append(f"${float(r['cost_total']):.4f}")
        table.add_row(*row)

    console.print(table)

    if len(results) >= 2:
        cheapest = min(results, key=lambda r: float(r["cost_per_call"]))
        expensive = max(results, key=lambda r: float(r["cost_per_call"]))
        if float(expensive["cost_per_call"]) > 0:
            ratio = float(expensive["cost_per_call"]) / float(cheapest["cost_per_call"])
            console.print(
                f"\n[dim]{expensive['model']} costs "
                f"{ratio:.1f}x more than {cheapest['model']}[/dim]"
            )


DEFAULT_MODELS = (
    "gpt-4o,gpt-4o-mini,claude-3-5-sonnet-latest,"
    "claude-3-5-haiku-latest,gemini-2.5-pro,gemini-2.5-flash"
)


def _estimate_tokens(text: str) -> int:
    """Uses tiktoken if available, else char-count heuristic."""
    try:
        import tiktoken  # type: ignore[import-untyped]

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return max(1, len(text) // 4)


@click.command()
@click.argument("prompt", required=False)
@click.option("--file", "prompt_file", type=click.Path(exists=True), help="Read prompt from file")
@click.option("--models", default=DEFAULT_MODELS, help="Comma-separated model list")
@click.option("--output-tokens", default=500, type=int, help="Estimated output tokens")
@click.option("--calls", default=1, type=int, help="Number of calls to estimate")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def calc(prompt, prompt_file, models, output_tokens, calls, as_json):
    """Calculate cost for a prompt across multiple models.

    Examples:
        forecost calc "Explain quantum computing in simple terms"
        forecost calc --file prompt.txt --models gpt-4o,claude-3-5-sonnet-latest
        forecost calc "Hello" --output-tokens 2000 --calls 1000
    """
    prompt = _read_prompt(prompt, prompt_file)

    if not prompt:
        console.print("[red]Provide a prompt string or --file path[/red]")
        raise SystemExit(1)

    input_tokens = _estimate_tokens(prompt)
    model_list = [m.strip() for m in models.split(",") if m.strip()]

    results = _build_results(model_list, input_tokens, output_tokens, calls)

    if as_json:
        _print_json_output(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            calls=calls,
            results=results,
        )
        return

    _print_table_output(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        calls=calls,
        results=results,
    )
