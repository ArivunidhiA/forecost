import click

from forecost.db import count_unscrubbed_legacy_rows, get_or_create_db, scrub_legacy_rows


@click.command()
@click.option("--check", is_flag=True, help="Only count rows that still hold raw values.")
@click.confirmation_option(prompt="Rewrite legacy rows in place (raw paths/metadata are lost)?")
def scrub(check: bool) -> None:
    """Pseudonymize raw paths and bound free-form metadata already in legacy costs.db."""
    conn = get_or_create_db()
    pending = count_unscrubbed_legacy_rows(conn)
    if check or pending == 0:
        click.echo(f"{pending} legacy row(s) still hold raw project paths, names, or metadata.")
        return
    changed = scrub_legacy_rows(conn)
    click.echo(
        f"Scrubbed {changed} legacy row(s). Back up costs.db first if you need the originals."
    )
