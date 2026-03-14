"""Auto-tracking via httpx monkey-patching. Non-blocking, transport-level."""

import os
from datetime import datetime, timezone
from typing import Callable

from llmlab.db import WriteQueue
from llmlab.pricing import calculate_cost, get_provider

__all__ = [
    "install",
    "uninstall",
    "set_project_id",
    "set_on_usage",
    "log_stream_usage",
    "get_interceptor_stats",
]

_original_send = None
_original_async_send = None
_current_project_id: int | None = None
_on_usage: Callable[..., None] | None = None
_write_queue: WriteQueue | None = None
_calls_tracked: int = 0
_calls_skipped_streaming: int = 0
_errors_count: int = 0


def _get_queue() -> WriteQueue:
    global _write_queue
    if _write_queue is None:
        _write_queue = WriteQueue()
    return _write_queue


def _log_internal_error(e: Exception) -> None:
    log_dir = os.path.expanduser("~/.llmlab")
    log_path = os.path.join(log_dir, "error.log")
    try:
        os.makedirs(log_dir, exist_ok=True)
        try:
            if os.path.getsize(log_path) > 1_000_000:
                with open(log_path, "r") as rf:
                    lines = rf.readlines()[-100:]
                with open(log_path, "w") as wf:
                    wf.writelines(lines)
        except OSError:
            pass
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(log_path, "a") as f:
            f.write(f"{ts} [interceptor] {e!r}\n")
    except OSError:
        pass


def _extract_usage(data: dict) -> tuple[int, int, str] | None:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    if "prompt_tokens" in usage and "completion_tokens" in usage:
        return (
            int(usage["prompt_tokens"]),
            int(usage["completion_tokens"]),
            "openai",
        )
    if "input_tokens" in usage and "output_tokens" in usage:
        return (
            int(usage["input_tokens"]),
            int(usage["output_tokens"]),
            "anthropic",
        )
    return None


def _extract_model(data: dict) -> str:
    for key in ("model", "id"):
        if key in data and isinstance(data[key], str):
            return data[key]
    for choice in data.get("choices", []) or []:
        if isinstance(choice, dict) and "message" in choice:
            msg = choice["message"]
            if isinstance(msg, dict) and "model" in msg:
                return msg["model"]
    return "unknown"


def _is_streaming(response) -> bool:
    ct = response.headers.get("content-type", "")
    return ct.startswith("text/event-stream")


def _extract_and_log_usage(response) -> None:
    global _calls_tracked, _calls_skipped_streaming
    if _is_streaming(response):
        _calls_skipped_streaming += 1
        return
    try:
        data = response.json()
    except Exception:
        return
    extracted = _extract_usage(data)
    if extracted is None:
        return
    tokens_in, tokens_out, _ = extracted
    model = _extract_model(data)
    provider = get_provider(model)
    cost = calculate_cost(model, tokens_in, tokens_out)
    project_id = _current_project_id
    if project_id is None:
        return
    ts = datetime.now(timezone.utc).isoformat()
    _get_queue().put(project_id, ts, model, provider, tokens_in, tokens_out, cost, None)
    _calls_tracked += 1
    if _on_usage:
        try:
            _on_usage(
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost=cost,
            )
        except Exception:
            pass


def _patched_send(self, *args, **kwargs):
    global _errors_count
    response = _original_send(self, *args, **kwargs)
    try:
        _extract_and_log_usage(response)
    except Exception as e:
        _errors_count += 1
        _log_internal_error(e)
    return response


async def _patched_async_send(self, *args, **kwargs):
    global _errors_count
    response = await _original_async_send(self, *args, **kwargs)
    try:
        _extract_and_log_usage(response)
    except Exception as e:
        _errors_count += 1
        _log_internal_error(e)
    return response


def log_stream_usage(response_data: dict) -> None:
    """Log usage from a streaming response after it has been consumed.

    Call this after reading all chunks from a streaming LLM API call.
    Pass the final accumulated response dict containing a "usage" key.
    """
    try:
        extracted = _extract_usage(response_data)
        if extracted is None:
            return
        tokens_in, tokens_out, _ = extracted
        model = _extract_model(response_data)
        provider = get_provider(model)
        cost = calculate_cost(model, tokens_in, tokens_out)
        project_id = _current_project_id
        if project_id is None:
            return
        ts = datetime.now(timezone.utc).isoformat()
        _get_queue().put(project_id, ts, model, provider, tokens_in, tokens_out, cost, None)
        if _on_usage:
            try:
                _on_usage(model=model, tokens_in=tokens_in, tokens_out=tokens_out, cost=cost)
            except Exception:
                pass
    except Exception as e:
        _log_internal_error(e)


def get_interceptor_stats() -> dict:
    return {
        "calls_tracked": _calls_tracked,
        "calls_skipped_streaming": _calls_skipped_streaming,
        "errors": _errors_count,
    }


def set_project_id(project_id: int | None) -> None:
    global _current_project_id
    _current_project_id = project_id


def set_on_usage(callback: Callable[..., None] | None) -> None:
    global _on_usage
    _on_usage = callback


def install(on_usage: Callable[..., None] | None = None) -> None:
    global _original_send, _original_async_send, _on_usage
    if os.environ.get("LLMLAB_DISABLED", "").lower() in ("1", "true", "yes"):
        return
    import httpx

    if _original_send is not None:
        return
    _original_send = httpx.Client.send
    _original_async_send = httpx.AsyncClient.send
    _on_usage = on_usage
    httpx.Client.send = _patched_send
    httpx.AsyncClient.send = _patched_async_send


def uninstall() -> None:
    global _original_send, _original_async_send
    import httpx

    if _original_send is None:
        return
    httpx.Client.send = _original_send
    httpx.AsyncClient.send = _original_async_send
    _original_send = None
    _original_async_send = None
