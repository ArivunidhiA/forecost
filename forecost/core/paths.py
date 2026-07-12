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

import os
from pathlib import Path


def forecost_home() -> Path:
    override = os.environ.get("FORECOST_HOME")
    if override:
        return Path(override)
    return Path.home() / ".forecost"
