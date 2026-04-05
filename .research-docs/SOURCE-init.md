# Core Source: forecost/__init__.py

Public API exports with lazy loading pattern to minimize import overhead.

```python
"""forecost - Know exactly what your AI project will cost."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

__version__ = "0.2.0"

if TYPE_CHECKING:
    from forecost.interceptor import get_interceptor_stats as get_interceptor_stats
    from forecost.tracker import (
        auto_track as auto_track,
    )
    from forecost.tracker import (
        get_session_summary as get_session_summary,
    )
    from forecost.tracker import (
        log_call as log_call,
    )
    from forecost.tracker import (
        log_stream_usage as log_stream_usage,
    )
    from forecost.tracker import (
        track as track,
    )
    from forecost.tracker import (
        track_cost as track_cost,
    )

    def disable() -> None: ...


__all__ = [
    "auto_track",
    "track_cost",
    "track",
    "log_call",
    "log_stream_usage",
    "get_session_summary",
    "get_interceptor_stats",
    "disable",
    "__version__",
]


def __getattr__(name: str):
    if name in (
        "auto_track",
        "track_cost",
        "track",
        "log_call",
        "log_stream_usage",
        "get_session_summary",
    ):
        import forecost.tracker as _tracker

        return getattr(_tracker, name)
    if name == "get_interceptor_stats":
        from forecost.interceptor import get_interceptor_stats

        return get_interceptor_stats
    if name == "disable":
        from forecost.interceptor import uninstall

        def _disable() -> None:
            uninstall()
            os.environ["FORECOST_DISABLED"] = "1"

        return _disable
    raise AttributeError(f"module 'forecost' has no attribute {name}")
```

---

## Design Notes

### Lazy Loading Pattern

**Problem:** `import forecost` should not eagerly import heavy modules (httpx, click, etc.) just to access `__version__`.

**Solution:** `__getattr__` PEP 562 implementation - imports happen on first attribute access.

**Import path for each export:**
- `auto_track`, `track_cost`, `track`, `log_call`, `log_stream_usage`, `get_session_summary` → `forecost.tracker`
- `get_interceptor_stats` → `forecost.interceptor`
- `disable` → creates closure calling `uninstall()` + sets environment variable

### TYPE_CHECKING Block

**Purpose:** Type checkers see the exports for static analysis, but runtime avoids actual imports.

**Pattern:** Uses `as` syntax (e.g., `auto_track as auto_track`) to satisfy type checkers without creating runtime imports.

### Disable Function

**Behavior:**
1. Calls `uninstall()` to restore original httpx.Client.send
2. Sets `FORECOST_DISABLED=1` to prevent re-installation
3. Used in tests via `FORECOST_DISABLED=1` environment variable
