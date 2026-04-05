"""Public tracking API for LLM cost tracking."""

from __future__ import annotations

import functools
import inspect
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from forecost import interceptor
from forecost.db import get_project_by_path
from forecost.pricing import calculate_cost, get_provider

if TYPE_CHECKING:
    pass

__all__ = [
    "auto_track",
    "track_cost",
    "track",
    "log_call",
    "log_stream_usage",
    "get_session_summary",
]

_session_stats: dict[str, Any] = {}
_stats_lock = threading.Lock()
_cached_project: dict | None = None
_project_cache_set = False
_project_cache_time: float = 0.0
_PROJECT_CACHE_TTL = 300.0  # 5 minutes

if sys.version_info >= (3, 11):
    import tomllib as _toml_loader
else:
    import tomli as _toml_loader


def _get_queue():
    """Reuse the interceptor module's WriteQueue (single shared queue)."""
    return interceptor._get_queue()


def _find_project() -> dict | None:
    global _cached_project, _project_cache_set, _project_cache_time
    if _project_cache_set and (time.monotonic() - _project_cache_time) < _PROJECT_CACHE_TTL:
        return _cached_project

    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        toml_path = parent / ".forecost.toml"
        if toml_path.is_file():
            try:
                with open(toml_path, "rb") as f:
                    data = _toml_loader.load(f)
            except Exception:
                _cached_project = None
                _project_cache_set = True
                _project_cache_time = time.monotonic()
                return None
            toml_dir = str(toml_path.parent)
            path = data.get("path", ".")
            if path == ".":
                project_path = toml_dir
            else:
                resolved = (Path(toml_dir) / path).resolve()
                try:
                    resolved.relative_to(Path(toml_dir).resolve())
                except ValueError:
                    _cached_project = None
                    _project_cache_set = True
                    _project_cache_time = time.monotonic()
                    return None
                project_path = str(resolved)
            result = get_project_by_path(os.path.abspath(project_path))
            _cached_project = result
            _project_cache_set = True
            _project_cache_time = time.monotonic()
            return result

    _cached_project = None
    _project_cache_set = True
    _project_cache_time = time.monotonic()
    return None


def _clear_project_cache() -> None:
    """Reset the cached project lookup. Used in tests."""
    global _cached_project, _project_cache_set, _project_cache_time
    _cached_project = None
    _project_cache_set = False
    _project_cache_time = 0.0


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
    """Auto-install tracking when a project config is discoverable in parent directories."""
    if os.environ.get("FORECOST_DISABLED", "").lower() in ("1", "true", "yes"):
        return
    proj = _find_project()
    if proj:
        interceptor.set_project_id(proj["id"])
        interceptor.install(on_usage=_record_usage)
    else:
        import sys

        print(
            "forecost: no .forecost.toml found in current or parent directories. "
            "Tracking disabled. Run 'forecost init' in your project root.",
            file=sys.stderr,
        )


def log_stream_usage(response_data: dict) -> None:
    """Log usage extracted from a consumed streaming response payload.

    Args:
        response_data: Final accumulated response dictionary containing usage fields.
    """
    interceptor.log_stream_usage(response_data)


def track_cost(provider: str = "openai"):
    """Decorator factory that records usage from dict-like LLM responses.

    Args:
        provider: Retained for API compatibility; provider is inferred from model at runtime.

    Returns:
        Callable: Decorator wrapping sync or async call sites.
    """

    def _process_result(result):
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

    def decorator(fn: Callable):
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                result = await fn(*args, **kwargs)
                _process_result(result)
                return result

            return async_wrapper

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            _process_result(result)
            return result

        return wrapper

    return decorator


@contextmanager
def track():
    """Yield a lightweight imperative tracker object for manual call logging.

    Yields:
        Tracker: Object exposing ``log_call`` for direct usage accounting.
    """

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
    """Record one model call in session stats and project usage logs.

    Args:
        model: Model identifier.
        tokens_in: Input token count.
        tokens_out: Output token count.
        provider: Retained for API compatibility; provider is inferred from model.
        metadata: Optional metadata dictionary to persist with the usage row.
    """
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
    """Return an aggregate summary of usage observed in the current process.

    Returns:
        dict: Totals for cost, tokens, calls, and per-model breakdown.
    """
    with _stats_lock:
        if not _session_stats:
            return {"total_cost": 0.0, "total_tokens": 0, "calls": 0, "by_model": {}}
        return dict(_session_stats)
