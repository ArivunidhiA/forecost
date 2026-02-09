"""Budget command - View and set monthly budget."""

import click

from ..config import is_authenticated
from ..api import get_budgets, create_budget, APIError, AuthenticationError, NetworkError


@click.command()
@click.argument("amount", type=float, required=False)
@click.option("--threshold", "-t", type=float, default=80.0, help="Alert threshold percentage (default: 80)")
def budget(amount: float, threshold: float):
    """View or set your monthly budget.

    \b
    Examples:
      llmlab budget              # View current budget
      llmlab budget 100          # Set budget to $100/month
      llmlab budget 50 -t 90    # Set $50 budget, alert at 90%
    """
    if not is_authenticated():
        click.echo(click.style("Not logged in.", fg="red"))
        click.echo("  Run 'llmlab login' first.")
        raise click.Abort()

    try:
        if amount is None:
            # View current budget
            result = get_budgets()
            budgets = result.get("budgets", [])

            if not budgets:
                click.echo(click.style("\nNo budget set.", fg="yellow"))
                click.echo("  Set one with: llmlab budget <amount>")
                click.echo()
                return

            b = budgets[0]
            click.echo(click.style("\nMonthly Budget", fg="cyan", bold=True))
            click.echo()
            click.echo(f"  Limit:     ${b['amount_usd']:.2f}")
            click.echo(f"  Spent:     ${b['current_spend']:.2f}")
            remaining = max(0, b['amount_usd'] - b['current_spend'])
            click.echo(f"  Remaining: ${remaining:.2f}")
            click.echo(f"  Alert at:  {b['alert_threshold']}%")

            status = b.get("status", "ok")
            if status == "exceeded":
                click.echo(click.style(f"  Status:    EXCEEDED", fg="red", bold=True))
            elif status == "warning":
                click.echo(click.style(f"  Status:    WARNING", fg="yellow", bold=True))
            else:
                click.echo(click.style(f"  Status:    OK", fg="green"))
            click.echo()

        else:
            # Set budget
            result = create_budget(amount, threshold)
            click.echo(click.style(f"\nBudget set to ${amount:.2f}/month", fg="green"))
            click.echo(f"  Alert threshold: {threshold}%")
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
