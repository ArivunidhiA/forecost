"""Where forecost keeps its data. One source of truth, overridable for tests and
for users who want to relocate it.

Resolution order for the forecost home directory:
1. ``$FORECOST_HOME`` if set (absolute path to the directory to use),
2. otherwise ``~/.forecost``.

Everything — the ledger, the legacy costs.db, the error log, policy.toml — hangs
off this one function so a single env var relocates all of it consistently
across platforms (``Path.home()`` differs between POSIX and Windows).
"""

from __future__ import annotations

import contextlib
import os
import re
from pathlib import Path

OWNERSHIP_MARKER = ".forecost-owned"
_OWNED_EXACT_NAMES = frozenset(
    {
        OWNERSHIP_MARKER,
        "costs.db",
        "costs.db-journal",
        "costs.db-shm",
        "costs.db-wal",
        "error.log",
        "ledger.db",
        "ledger.db-journal",
        "ledger.db-shm",
        "ledger.db-wal",
        "legacy-recovery.jsonl",
        "legacy-recovery.replayed.jsonl",
        "policy.toml",
        "recovery.jsonl",
        "recovery.replayed.jsonl",
    }
)
_OWNED_GENERATED_NAME = re.compile(
    r"(?:legacy-)?recovery(?:\.replayed(?:\.\d+)?)?\.jsonl"
    r"|(?:legacy-)?recovery\.\d+\.\d+\.[0-9a-f]{32}\.jsonl"
)


class UnownedDataRootError(RuntimeError):
    """A custom FORECOST_HOME points at a directory Forecost does not own."""


def forecost_home() -> Path:
    override = os.environ.get("FORECOST_HOME")
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise ValueError("FORECOST_HOME must be an absolute path")
        return path
    return Path.home() / ".forecost"


def _is_owned_entry(entry: Path) -> bool:
    return (
        entry.name in _OWNED_EXACT_NAMES or _OWNED_GENERATED_NAME.fullmatch(entry.name) is not None
    )


def _validate_custom_home_ownership(
    path: Path, *, existed: bool, is_configured_home: bool, is_default_home: bool
) -> None:
    if not existed or not is_configured_home or is_default_home:
        return
    entries = list(path.iterdir())
    marker = path / OWNERSHIP_MARKER
    if entries and not marker.is_file() and any(not _is_owned_entry(entry) for entry in entries):
        raise UnownedDataRootError(
            "custom FORECOST_HOME is nonempty and has no Forecost ownership marker"
        )


def _should_claim_data_root(
    path: Path, *, existed: bool, is_configured_home: bool, is_default_home: bool
) -> bool:
    if not existed or not any(path.iterdir()):
        return True
    marker = path / OWNERSHIP_MARKER
    return is_default_home or marker.is_file() or is_configured_home


def _lock_owned_data_root(path: Path) -> None:
    marker = path / OWNERSHIP_MARKER
    with contextlib.suppress(OSError):
        marker.touch(exist_ok=True)
        marker.chmod(0o600)
        path.chmod(0o700)


def ensure_private_dir(path: Path) -> Path:
    """Create ``path`` (and parents) and make it owner-only (0700).

    Best-effort and idempotent: the chmod runs even when the directory already
    existed with looser permissions (the plain ``mkdir(mode=…)`` only applies to
    newly-created dirs and is masked by umask). The ledger stores spend and
    project-path metadata, so the tree must not be world-readable."""
    existed = path.exists()
    resolved_path = path.resolve()
    is_configured_home = resolved_path == forecost_home().resolve()
    is_default_home = resolved_path == (Path.home() / ".forecost").resolve()
    _validate_custom_home_ownership(
        path,
        existed=existed,
        is_configured_home=is_configured_home,
        is_default_home=is_default_home,
    )
    path.mkdir(parents=True, exist_ok=True)
    if _should_claim_data_root(
        path,
        existed=existed,
        is_configured_home=is_configured_home,
        is_default_home=is_default_home,
    ):
        _lock_owned_data_root(path)
    return path


def chmod_private(path: Path) -> None:
    """Make a file owner-only (0600) if it exists. Best-effort, never raises."""
    with contextlib.suppress(OSError):
        if path.exists():
            path.chmod(0o600)
