"""llmcast - Know exactly what your AI project will cost."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

__version__ = "0.1.0"

if TYPE_CHECKING:
    from llmcast.interceptor import get_interceptor_stats as get_interceptor_stats
    from llmcast.tracker import (
        auto_track as auto_track,
    )
    from llmcast.tracker import (
        get_session_summary as get_session_summary,
    )
    from llmcast.tracker import (
        log_call as log_call,
    )
    from llmcast.tracker import (
        log_stream_usage as log_stream_usage,
    )
    from llmcast.tracker import (
        track as track,
    )
    from llmcast.tracker import (
        track_cost as track_cost,
    )

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
        import llmcast.tracker as _tracker

        return getattr(_tracker, name)
    if name == "get_interceptor_stats":
        from llmcast.interceptor import get_interceptor_stats

        return get_interceptor_stats
    if name == "disable":
        from llmcast.interceptor import uninstall

        def _disable() -> None:
            uninstall()
            os.environ["LLMLAB_DISABLED"] = "1"

        return _disable
    raise AttributeError(f"module 'llmcast' has no attribute {name}")
