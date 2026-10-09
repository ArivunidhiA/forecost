"""forecost pricing-update — opt-in refresh of the pricing overlay.

The only network call in the product, and only when the user runs this command. It downloads one
public JSON file (no user data is sent), validates it strictly, and stores it in
``$FORECOST_HOME/pricing.json``. A copy older than the bundled data is ignored at load time.
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import click

from forecost.core.paths import ensure_private_dir, forecost_home
from forecost.pricing_data import (
    LOCAL_NAME,
    MAX_BYTES,
    PricingDataError,
    age_days,
    load_effective,
    validate,
)

DEFAULT_URL = (
    "https://raw.githubusercontent.com/ArivunidhiA/forecost/main/forecost/data/pricing.json"
)


def _fetch(source: str) -> object:
    if source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=30) as response:  # noqa: S310  # nosec B310
            payload = response.read(MAX_BYTES + 1)
    else:
        payload = Path(source).read_bytes()
    if len(payload) > MAX_BYTES:
        raise PricingDataError("pricing data too large")
    return json.loads(payload)


@click.command("pricing-update")
@click.option("--source", default=DEFAULT_URL, show_default=True, help="https URL or local file.")
@click.option("--dry-run", is_flag=True, help="Validate and report without writing.")
def pricing_update(source: str, dry_run: bool) -> None:
    """Fetch the latest published pricing data (opt-in; the only network access)."""
    if source.startswith("http://"):
        raise click.ClickException("refusing non-https pricing source")
    try:
        document = validate(_fetch(source))
    except (OSError, urllib.error.URLError, ValueError) as error:
        raise click.ClickException(
            f"could not load pricing data: {type(error).__name__}"
        ) from error
    _, current = load_effective()
    stamp = document["generated_at"]
    models = document["models"]
    if current and stamp < current:
        click.echo(f"Already newer ({current}) than the source ({stamp}); nothing to do.")
        return
    if dry_run:
        click.echo(f"Valid: {len(models)} models, generated {stamp}. Dry run, nothing written.")
        return
    home = forecost_home()
    ensure_private_dir(home)
    handle, temporary = tempfile.mkstemp(prefix=".pricing.", suffix=".tmp", dir=home)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=1, sort_keys=True)
        os.chmod(temporary, 0o600)
        os.replace(temporary, home / LOCAL_NAME)
    finally:
        Path(temporary).unlink(missing_ok=True)
    click.echo(
        f"Updated pricing overlay: {len(models)} models, generated {stamp} (age "
        f"{age_days(stamp)} day(s)). New events use these rates."
    )
