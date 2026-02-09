"""LLMLab CLI - Main entry point."""

import click

from . import __version__
from .commands.login import login
from .commands.logout import logout
from .commands.configure import configure
from .commands.proxy_key import proxy_key
from .commands.stats import stats
from .commands.budget import budget
from .commands.optimize import optimize
from .commands.export import export_cmd


@click.group()
@click.version_option(version=__version__, prog_name="llmlab")
def cli():
    """LLMLab - Unified API gateway for LLM providers.
    
    Route all your LLM API calls through a single endpoint.
    Track costs, manage keys, and switch providers seamlessly.
    
    Get started:
    
      $ llmlab login          # Authenticate with GitHub
      $ llmlab configure      # Add your API keys
      $ llmlab proxy-key      # Get your proxy key
      $ llmlab stats          # View usage statistics
      $ llmlab budget 100     # Set monthly budget
      $ llmlab optimize       # Get cost optimization tips
      $ llmlab export         # Export costs to CSV
    """
    pass


# Register commands
cli.add_command(login)
cli.add_command(logout)
cli.add_command(configure)
cli.add_command(proxy_key)
cli.add_command(stats)
cli.add_command(budget)
cli.add_command(optimize)
cli.add_command(export_cmd)


if __name__ == "__main__":
    cli()
