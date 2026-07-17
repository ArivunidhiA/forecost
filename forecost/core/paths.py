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
from pathlib import Path


def forecost_home() -> Path:
    override = os.environ.get("FORECOST_HOME")
    if override:
        return Path(override)
    return Path.home() / ".forecost"


def ensure_private_dir(path: Path) -> Path:
    """Create ``path`` (and parents) and make it owner-only (0700).

    Best-effort and idempotent: the chmod runs even when the directory already
    existed with looser permissions (the plain ``mkdir(mode=…)`` only applies to
    newly-created dirs and is masked by umask). The ledger stores spend and
    project-path metadata, so the tree must not be world-readable."""
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.chmod(0o700)
    return path


def chmod_private(path: Path) -> None:
    """Make a file owner-only (0600) if it exists. Best-effort, never raises."""
    with contextlib.suppress(OSError):
        if path.exists():
            path.chmod(0o600)
