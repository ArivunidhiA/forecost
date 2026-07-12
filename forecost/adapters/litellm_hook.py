"""LiteLLM proxy integration: budget gate (pre-call) + ledger ingestion (post-call).

Usage in a LiteLLM proxy config:

    # custom_callbacks.py (next to your litellm config.yaml)
    from forecost.adapters.litellm_hook import ForecostLogger
    proxy_handler_instance = ForecostLogger()

    # config.yaml
    litellm_settings:
      callbacks: custom_callbacks.proxy_handler_instance

Semantics (BASEMENT.md law L4 applied to the gateway lane):
- The pre-call hook evaluates the ledger-backed policy and REJECTS the request
  (returns an error string, which LiteLLM turns into a 400 to the caller) only
  on a genuine `deny` decision. Any internal forecost failure fails OPEN by
  default — a broken forecost must never take down the gateway. Gateway
  operators who prefer fail-closed must opt in via policy.mode='ci'.
- The success hook emits one UsageEvent per completed call, carrying LiteLLM's
  own computed `response_cost` as a source-reported posting alongside the
  pricing-table posting — the two-books structure that makes reconciliation
  possible later.

Requires: pip install litellm (deliberately NOT a forecost dependency —
lazy-imported so the core package stays lightweight).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

try:
    # litellm is an optional dependency, deliberately absent from forecost's own
    # requirements — the ignore below keeps type checking green either way.
    from litellm.integrations.custom_logger import (  # pyright: ignore[reportMissingImports]
        CustomLogger,
    )
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "The LiteLLM adapter requires litellm. Install it with: pip install litellm"
    ) from _exc

from pathlib import Path

from forecost.adapters.base import Money, UsageEvent
from forecost.core.errlog import log_error
from forecost.ledger.db import get_ledger_db
from forecost.ledger.sink import SyncLedgerSink
from forecost.policy.engine import evaluate
from forecost.policy.rules import load_policy_file


class ForecostLogger(CustomLogger):
    """LiteLLM CustomLogger wiring forecost's policy engine and ledger into the proxy."""

    def __init__(self, policy_path: Path | None = None, ledger_path: Path | None = None) -> None:
        super().__init__()
        from forecost.core.paths import forecost_home

        self._policy_path = policy_path or (forecost_home() / "policy.toml")
        self._ledger_path = ledger_path
        self._sink: SyncLedgerSink | None = None

    def _get_sink(self) -> SyncLedgerSink:
        if self._sink is None:
            self._sink = SyncLedgerSink(ledger_path=self._ledger_path)
        return self._sink

    async def async_pre_call_hook(
        self, user_api_key_dict: Any, cache: Any, data: dict, call_type: str
    ):
        """Budget gate. Returns an error string to reject, or the data to allow."""
        try:
            conn = get_ledger_db(self._ledger_path)
            policy = load_policy_file(self._policy_path)
            decision = evaluate(conn, policy, agent="litellm")
            if decision.action == "deny":
                return f"forecost budget gate: {decision.reason}"
            return data
        except Exception as exc:  # nosec B110 - fail-open: gateway must never break
            log_error("adapters.litellm.pre_call", f"gate failed open: {exc!r}")
            return data

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time) -> None:
        """Emit one UsageEvent per completed call, with LiteLLM's cost as source-reported."""
        try:
            self._get_sink().emit(_kwargs_to_event(kwargs, response_obj))
        except Exception as exc:  # nosec B110 - ingestion must never break the gateway
            log_error("adapters.litellm.success", f"ingest failed: {exc!r}")


def _usage_tokens(response_obj: Any) -> tuple[int, int]:
    raw_usage = getattr(response_obj, "usage", None) if response_obj is not None else None
    if raw_usage is None:
        return 0, 0
    return (
        getattr(raw_usage, "prompt_tokens", 0) or 0,
        getattr(raw_usage, "completion_tokens", 0) or 0,
    )


def _kwargs_to_event(kwargs: dict, response_obj: Any) -> UsageEvent:
    call_id = kwargs.get("litellm_call_id") or str(uuid.uuid4())
    tokens_in, tokens_out = _usage_tokens(response_obj)
    response_cost = kwargs.get("response_cost")
    reported = (
        Money(amount=float(response_cost), currency="USD") if response_cost is not None else None
    )
    user_id = (kwargs.get("litellm_params", {}).get("metadata") or {}).get("user_api_key_user_id")
    return UsageEvent(
        event_uid=f"litellm:{call_id}",
        ts=datetime.now(timezone.utc),
        source="litellm",
        model=kwargs.get("model") or "unknown",
        provider=kwargs.get("custom_llm_provider"),
        session_uid=str(user_id) if user_id else None,
        run_id=call_id,
        agent="litellm",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        reported_cost=reported,
        metadata={"call_type": kwargs.get("call_type")},
    )
