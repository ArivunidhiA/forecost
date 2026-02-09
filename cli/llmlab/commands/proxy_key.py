"""Proxy key command - Get unified API key."""

import click

from ..config import is_authenticated
from ..api import get_proxy_keys, APIError, AuthenticationError, NetworkError


@click.command("proxy-key")
@click.option("--format", "-f", "output_format", 
              type=click.Choice(["shell", "env", "json", "plain"]),
              default="shell",
              help="Output format")
@click.option("--provider", "-p", default="openai",
              help="Provider format for the export (default: openai)")
def proxy_key(output_format: str, provider: str):
    """Get your unified proxy API key.
    
    The proxy key routes all requests through LLMLab, enabling:
    - Unified billing across all providers
    - Automatic cost tracking
    - Model routing and fallbacks
    
    \b
    Usage in your code:
      export OPENAI_API_KEY=$(llmlab proxy-key --format=plain)
      
    Or source directly:
      eval $(llmlab proxy-key)
    """
    if not is_authenticated():
        click.echo(click.style("✗ Not logged in.", fg="red"))
        click.echo("  Run 'llmlab login' first.")
        raise click.Abort()
    
    try:
        result = get_proxy_keys()
        keys = result.get("keys", [])
        
        # Find key matching provider
        matching_key = None
        for k in keys:
            if k.get("provider") == provider:
                matching_key = k.get("proxy_key")
                break
        
        if not matching_key and keys:
            matching_key = keys[0].get("proxy_key")
        
        proxy_key_value = matching_key
        
        if not proxy_key_value:
            click.echo(click.style("No proxy key available.", fg="red"))
            click.echo("  Configure your API keys first: llmlab configure --sync")
            raise click.Abort()
        
        # Map provider to env var
        env_vars = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "all": None,  # Show all
        }
        
        env_var = env_vars.get(provider, "OPENAI_API_KEY")
        
        # Output based on format
        if output_format == "plain":
            click.echo(proxy_key_value)
        
        elif output_format == "json":
            import json
            output = {
                "key": proxy_key_value,
                "provider": provider,
                "base_url": "https://api.llmlab.dev/v1",
            }
            click.echo(json.dumps(output, indent=2))
        
        elif output_format == "env":
            # .env file format
            click.echo(f'{env_var}="{proxy_key_value}"')
            click.echo('LLMLAB_BASE_URL="https://api.llmlab.dev/v1"')
        
        else:  # shell (default)
            click.echo(f"export {env_var}={proxy_key_value}")
            click.echo("export LLMLAB_BASE_URL=https://api.llmlab.dev/v1")
            click.echo()
            click.echo(click.style("# Tip: eval $(llmlab proxy-key) to set automatically", 
                                  fg="bright_black"))
    
    except AuthenticationError as e:
        click.echo(click.style(f"✗ {e.message}", fg="red"))
        raise click.Abort()
    except NetworkError as e:
        click.echo(click.style(f"✗ {e.message}", fg="red"))
        raise click.Abort()
    except APIError as e:
        click.echo(click.style(f"✗ {e.message}", fg="red"))
        raise click.Abort()
