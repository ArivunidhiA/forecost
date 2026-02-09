"""Optimize command - Show cost optimization recommendations."""

import click

from ..config import is_authenticated
from ..api import get_recommendations, APIError, AuthenticationError, NetworkError


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def optimize(as_json: bool):
    """Show cost optimization recommendations.

    Analyzes your usage patterns and suggests ways to reduce costs.

    \b
    Examples:
      llmlab optimize           # Show recommendations
      llmlab optimize --json    # Output as JSON
    """
    if not is_authenticated():
        click.echo(click.style("Not logged in.", fg="red"))
        click.echo("  Run 'llmlab login' first.")
        raise click.Abort()

    try:
        with click.progressbar(length=1, label="Analyzing usage",
                              show_eta=False, show_percent=False) as bar:
            result = get_recommendations()
            bar.update(1)

        click.echo()

        if as_json:
            import json
            click.echo(json.dumps(result, indent=2))
            return

        recommendations = result.get("recommendations", [])
        total_savings = result.get("total_potential_savings", 0)

        click.echo(click.style("Cost Optimization Recommendations", fg="cyan", bold=True))
        click.echo()

        if not recommendations:
            click.echo(click.style("No recommendations yet.", fg="yellow"))
            click.echo("  Start making API calls through your proxy keys to get personalized tips.")
            click.echo()
            return

        for i, rec in enumerate(recommendations, 1):
            title = rec.get("title", "Recommendation")
            description = rec.get("description", "")
            savings = rec.get("potential_savings", 0)
            priority = rec.get("priority", "medium")

            # Priority color
            priority_color = {"high": "red", "medium": "yellow", "low": "green"}.get(priority, "white")

            click.echo(f"  {i}. {click.style(title, fg='bright_white', bold=True)}")
            click.echo(f"     {description}")
            click.echo(f"     Priority: {click.style(priority.upper(), fg=priority_color)}", nl=False)
            if savings > 0:
                click.echo(f"  |  Potential savings: {click.style(f'${savings:.2f}/mo', fg='green')}")
            else:
                click.echo()
            click.echo()

        if total_savings > 0:
            click.echo(
                click.style(
                    f"  Total potential monthly savings: ${total_savings:.2f}",
                    fg="green",
                    bold=True,
                )
            )
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
