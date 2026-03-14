"""Public tracking API for LLM cost tracking."""

from __future__ import annotations

import functools
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from llmlab import interceptor
from llmlab.db import WriteQueue, get_project_by_path
from llmlab.pricing import calculate_cost, get_provider

if TYPE_CHECKING:
    pass

__all__ = [
    "auto_track",
    "track_cost",
    "track",
    "log_call",
    "log_stream_usage",
    "get_session_summary",
    "_clear_project_cache",
]

_write_queue: WriteQueue | None = None
_session_stats: dict[str, Any] = {}
_stats_lock = threading.Lock()
_cached_project: dict | None = None
_project_cache_set = False


def _get_queue() -> WriteQueue:
    global _write_queue
    if _write_queue is None:
        _write_queue = WriteQueue()
    return _write_queue


def _find_project() -> dict | None:
    global _cached_project, _project_cache_set
    if _project_cache_set:
        return _cached_project

    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        toml_path = parent / ".llmlab.toml"
        if toml_path.is_file():
            try:
                try:
                    import tomllib
                except ImportError:
                    import tomli as tomllib  # type: ignore[no-redef]
                with open(toml_path, "rb") as f:
                    data = tomllib.load(f)
            except Exception:
                _cached_project = None
                _project_cache_set = True
                return None
            toml_dir = str(toml_path.parent)
            path = data.get("path", ".")
            if path == ".":
                project_path = toml_dir
            else:
                resolved = (Path(toml_dir) / path).resolve()
                # Reject traversal outside the toml directory
                try:
                    resolved.relative_to(Path(toml_dir).resolve())
                except ValueError:
                    _cached_project = None
                    _project_cache_set = True
                    return None
                project_path = str(resolved)
            result = get_project_by_path(os.path.abspath(project_path))
            _cached_project = result
            _project_cache_set = True
            return result

    _cached_project = None
    _project_cache_set = True
    return None


def _clear_project_cache() -> None:
    """Reset the cached project lookup. Used in tests."""
    global _cached_project, _project_cache_set
    _cached_project = None
    _project_cache_set = False


def _record_usage(model: str, tokens_in: int, tokens_out: int, cost: float) -> None:
    with _stats_lock:
        if "total_cost" not in _session_stats:
            _session_stats.update(
                {
                    "total_cost": 0.0,
                    "total_tokens": 0,
                    "calls": 0,
                    "by_model": {},
                }
            )
        _session_stats["total_cost"] += cost
        _session_stats["total_tokens"] += tokens_in + tokens_out
        _session_stats["calls"] += 1
        by_model = _session_stats["by_model"]
        if model not in by_model:
            by_model[model] = {"cost": 0.0, "tokens": 0, "calls": 0}
        by_model[model]["cost"] += cost
        by_model[model]["tokens"] += tokens_in + tokens_out
        by_model[model]["calls"] += 1


def auto_track() -> None:
    if os.environ.get("LLMLAB_DISABLED", "").lower() in ("1", "true", "yes"):
        return
    proj = _find_project()
    if proj:
        interceptor.set_project_id(proj["id"])
    else:
        import sys

        print(
            "llmlab: no .llmlab.toml found in current or parent directories. "
            "Tracking disabled. Run 'llmlab init' in your project root.",
            file=sys.stderr,
        )
    interceptor.install(on_usage=_record_usage)


def log_stream_usage(response_data: dict) -> None:
    """Log usage from a consumed streaming response. Delegates to interceptor."""
    interceptor.log_stream_usage(response_data)


def track_cost(provider: str = "openai"):
    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            if isinstance(result, dict) and "usage" in result:
                usage = result["usage"]
                if isinstance(usage, dict):
                    tokens_in = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)))
                    tokens_out = int(usage.get("completion_tokens", usage.get("output_tokens", 0)))
                    model = result.get("model", result.get("id", "unknown"))
                    cost = calculate_cost(model, tokens_in, tokens_out)
                    _record_usage(model, tokens_in, tokens_out, cost)
                    proj = _find_project()
                    if proj:
                        ts = datetime.now(timezone.utc).isoformat()
                        _get_queue().put(
                            proj["id"],
                            ts,
                            model,
                            get_provider(model),
                            tokens_in,
                            tokens_out,
                            cost,
                            None,
                        )
            return result

        return wrapper

    return decorator


@contextmanager
def track():
    class Tracker:
        def log_call(
            self,
            model: str,
            tokens_in: int,
            tokens_out: int,
            provider: str = "openai",
            metadata: dict | None = None,
        ) -> None:
            cost = calculate_cost(model, tokens_in, tokens_out)
            _record_usage(model, tokens_in, tokens_out, cost)
            proj = _find_project()
            if proj:
                ts = datetime.now(timezone.utc).isoformat()
                meta_str = json.dumps(metadata) if metadata else None
                _get_queue().put(
                    proj["id"],
                    ts,
                    model,
                    get_provider(model),
                    tokens_in,
                    tokens_out,
                    cost,
                    meta_str,
                )

    yield Tracker()


def log_call(
    model: str,
    tokens_in: int,
    tokens_out: int,
    provider: str = "openai",
    metadata: dict | None = None,
) -> None:
    cost = calculate_cost(model, tokens_in, tokens_out)
    _record_usage(model, tokens_in, tokens_out, cost)
    proj = _find_project()
    if proj:
        ts = datetime.now(timezone.utc).isoformat()
        meta_str = json.dumps(metadata) if metadata else None
        _get_queue().put(
            proj["id"], ts, model, get_provider(model), tokens_in, tokens_out, cost, meta_str
        )


def get_session_summary() -> dict:
    with _stats_lock:
        if not _session_stats:
            return {"total_cost": 0.0, "total_tokens": 0, "calls": 0, "by_model": {}}
        return dict(_session_stats)
