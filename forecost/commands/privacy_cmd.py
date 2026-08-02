"""Inspectable local privacy checks for Forecost-owned state."""

from __future__ import annotations

from pathlib import Path

import click

from forecost.core.paths import forecost_home

_MAX_SCAN_BYTES = 32 * 1024 * 1024


@click.group()
def privacy() -> None:
    """Verify that a supplied content canary is absent from Forecost state."""


@privacy.command("verify")
@click.option("--canary", default="FORECOST-PRIVACY-CANARY", show_default=True)
@click.option("--home", "home_path", type=click.Path(path_type=Path), default=None)
def verify_privacy(canary: str, home_path: Path | None) -> None:
    """Scan Forecost-owned files for a test sentinel without persisting it."""
    if not canary or len(canary) > 512:
        raise click.ClickException("canary must be between 1 and 512 characters")
    root = (home_path or forecost_home()).expanduser().resolve()
    needle = canary.encode("utf-8")
    offenders: list[Path] = []
    scanned = 0
    if root.exists():
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                if path.stat().st_size > _MAX_SCAN_BYTES:
                    continue
                scanned += 1
                if needle in path.read_bytes():
                    offenders.append(path)
            except OSError:
                continue
    if offenders:
        raise click.ClickException(
            f"privacy canary found in {len(offenders)} Forecost-owned file(s): "
            + ", ".join(str(path) for path in offenders[:5])
        )
    click.echo(f"Privacy verify: clean ({scanned} file(s) scanned; canary not persisted).")
