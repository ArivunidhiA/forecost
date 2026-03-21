import os

import click
from rich.console import Console

from forecost.db import get_or_create_db, get_project_by_path

console = Console()


@click.command()
@click.option("--keep-data", is_flag=True, help="Keep usage logs, only reset baseline")
@click.confirmation_option(prompt="This will reset the project. Continue?")
def reset(keep_data):
    """Reset the current project."""
    project_path = os.path.abspath(os.getcwd())
    project = get_project_by_path(project_path)

    if project is None:
        console.print(
            f"[red]No forecost project found in {project_path}[/red]\n\n"
            "  Nothing to reset. Run [bold]forecost init[/bold] to start."
        )
        raise SystemExit(1)

    conn = get_or_create_db()
    pid = project["id"]

    if keep_data:
        conn.execute("DELETE FROM forecasts WHERE project_id = ?", (pid,))
        conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
        conn.commit()
        console.print(
            "[green]Project baseline reset.[/green] Usage logs preserved.\n"
            "  Run [bold]forecost init[/bold] to re-initialize."
        )
    else:
        conn.execute("DELETE FROM forecasts WHERE project_id = ?", (pid,))
        conn.execute("DELETE FROM usage_logs WHERE project_id = ?", (pid,))
        conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
        conn.commit()
        toml_path = os.path.join(project_path, ".forecost.toml")
        if os.path.exists(toml_path):
            os.remove(toml_path)
        console.print(
            "[green]Project fully reset.[/green]\n  Run [bold]forecost init[/bold] to start fresh."
        )
