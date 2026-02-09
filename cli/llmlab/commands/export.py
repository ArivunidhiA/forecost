"""Export command - Export usage logs to CSV or JSON via backend API."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from ..config import is_authenticated
from ..api import export_logs_csv, export_logs_json, APIError, AuthenticationError, NetworkError


@click.command("export")
@click.option("--period", "-p", type=click.Choice(["today", "week", "month", "all"]),
              default="month", help="Time period to export (default: month)")
@click.option("--output", "-o", help="Output file path")
@click.option("--json", "as_json", is_flag=True, help="Export as JSON instead of CSV")
@click.option("--provider", help="Filter by provider (openai, anthropic, google)")
@click.option("--model", help="Filter by model name")
def export_cmd(period: str, output: Optional[str], as_json: bool, provider: Optional[str], model: Optional[str]):
    """Export usage logs to CSV or JSON.

    \b
    Examples:
      llmlab export                           # Export as CSV
      llmlab export -o costs.csv              # Export to specific file
      llmlab export --json                    # Export as JSON
      llmlab export --provider openai         # Filter by provider
      llmlab export --model gpt-4o --json     # Filter by model, JSON format
    """
    if not is_authenticated():
        click.echo(click.style("Not logged in.", fg="red"))
        click.echo("  Run 'llmlab login' first.")
        raise click.Abort()

    try:
        with click.progressbar(length=1, label="Fetching data",
                              show_eta=False, show_percent=False) as bar:
            if as_json:
                data = export_logs_json(provider=provider, model=model)
            else:
                data = export_logs_csv(period=period, provider=provider, model=model)
            bar.update(1)

        click.echo()

        if not data or len(data) < 10:
            click.echo(click.style("No data to export for the selected filters.", fg="yellow"))
            return

        # Determine filename
        if not output:
            now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            ext = "json" if as_json else "csv"
            parts = [f"llmlab_export_{period}"]
            if provider:
                parts.append(provider)
            if model:
                parts.append(model.replace("/", "-"))
            output = f"{'_'.join(parts)}_{now}.{ext}"

        output_path = Path(output)
        output_path.write_bytes(data)

        click.echo(click.style(f"Exported to {output_path}", fg="green"))

        # Count lines for CSV as a summary
        if not as_json:
            line_count = data.count(b"\n") - 1  # subtract header
            click.echo(f"  Records: {max(0, line_count)}")
        else:
            click.echo(f"  Size: {len(data):,} bytes")

        if provider:
            click.echo(f"  Provider: {provider}")
        if model:
            click.echo(f"  Model: {model}")
        click.echo()

    except AuthenticationError as e:
        click.echo(click.style(f"Error: {e.message}", fg="red"))
        raise click.Abort()
    except NetworkError as e:
        click.echo(click.style(f"Error: {e.message}", fg="red"))
        raise click.Abort()
    except APIError as e:
        click.echo(click.style(f"Error: {e.message}", fg="red"))
        raise click.Abort()
    except IOError as e:
        click.echo(click.style(f"Failed to write file: {e}", fg="red"))
        raise click.Abort()
