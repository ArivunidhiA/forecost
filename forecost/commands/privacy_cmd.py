"""Inspectable local privacy checks for Forecost-owned state."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import click

from forecost.core.paths import forecost_home

_SCAN_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ScanResult:
    files: int
    bytes_scanned: int
    offenders: tuple[Path, ...]
    unreadable: tuple[Path, ...]
    skipped: tuple[Path, ...]


@click.group()
def privacy() -> None:
    """Check whether a supplied canary appears in one scanned Forecost root."""


def _contains_stream(path: Path, needle: bytes) -> tuple[bool, int]:
    """Scan one regular file in bounded memory, including chunk boundaries."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    total = 0
    overlap = b""
    try:
        while True:
            chunk = os.read(descriptor, _SCAN_CHUNK_BYTES)
            if not chunk:
                return False, total
            total += len(chunk)
            material = overlap + chunk
            if needle in material:
                return True, total
            overlap = material[-(len(needle) - 1) :] if len(needle) > 1 else b""
    finally:
        os.close(descriptor)


def _classify_entry(
    entry: os.DirEntry[str],
    pending: list[Path],
    regular: list[Path],
    unreadable: list[Path],
    skipped: list[Path],
) -> None:
    path = Path(entry.path)
    try:
        if entry.is_symlink():
            skipped.append(path)
        elif entry.is_dir(follow_symlinks=False):
            pending.append(path)
        elif entry.is_file(follow_symlinks=False):
            regular.append(path)
        else:
            skipped.append(path)
    except OSError:
        unreadable.append(path)


def _discover_owned_paths(root: Path) -> tuple[list[Path], list[Path], list[Path]]:
    regular: list[Path] = []
    unreadable: list[Path] = []
    skipped: list[Path] = []
    try:
        root_exists = root.exists()
    except OSError:
        # The scan result, not an implementation traceback, is the public
        # failure contract even when an ancestor prevents statting the root.
        return regular, [root], skipped
    pending = [root] if root_exists else []
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    _classify_entry(entry, pending, regular, unreadable, skipped)
        except OSError:
            # pathlib.Path.rglob may silently suppress directory traversal
            # failures. Explicit scandir accounting makes absence claims fail
            # closed when any owned subtree could not be inspected.
            unreadable.append(directory)
    return regular, unreadable, skipped


def _scan_regular_files(
    regular: list[Path], needle: bytes, unreadable: list[Path]
) -> tuple[list[Path], int]:
    offenders: list[Path] = []
    bytes_scanned = 0
    for path in regular:
        try:
            found, size = _contains_stream(path, needle)
            bytes_scanned += size
            if found:
                offenders.append(path)
        except OSError:
            unreadable.append(path)
    return offenders, bytes_scanned


def _scan(root: Path, needle: bytes) -> ScanResult:
    regular, unreadable, skipped = _discover_owned_paths(root)
    offenders, bytes_scanned = _scan_regular_files(regular, needle, unreadable)
    return ScanResult(
        len(regular),
        bytes_scanned,
        tuple(offenders),
        tuple(unreadable),
        tuple(skipped),
    )


def _validated_canary(canary: str) -> bytes:
    if not canary or len(canary) > 512:
        raise click.ClickException("canary must be between 1 and 512 characters")
    return canary.encode("utf-8")


def _raise_if_inconclusive(result: ScanResult) -> None:
    if result.offenders:
        raise click.ClickException(
            f"privacy canary found in {len(result.offenders)} Forecost-owned file(s): "
            + ", ".join(str(path) for path in result.offenders[:5])
        )
    if result.unreadable or result.skipped:
        examples = (*result.unreadable, *result.skipped)[:5]
        raise click.ClickException(
            "privacy scan inconclusive: "
            f"{len(result.unreadable)} unreadable and {len(result.skipped)} skipped "
            "non-regular/symlink path(s): " + ", ".join(str(path) for path in examples)
        )


@privacy.command("verify")
@click.option("--canary", default="FORECOST-PRIVACY-CANARY", show_default=True)
@click.option("--home", "home_path", type=click.Path(path_type=Path), default=None)
def verify_privacy(canary: str, home_path: Path | None) -> None:
    """Scan Forecost-owned files for a test sentinel without persisting it."""
    root = (home_path or forecost_home()).expanduser().resolve()
    result = _scan(root, _validated_canary(canary))
    _raise_if_inconclusive(result)
    click.echo(
        f"Privacy canary absent in scanned root ({result.files} file(s), "
        f"{result.bytes_scanned} byte(s), 0 skipped/unreadable); "
        "this is not end-to-end privacy proof."
    )
