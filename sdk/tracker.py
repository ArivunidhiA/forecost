"""
LLMLab Cost Tracker - Decorator and context manager for tracking LLM costs
"""

import functools
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .api_client import APIClient
from .config import get_config


class CostTracker:
    """Manages cost tracking for LLM API calls"""

    def __init__(self, api_client: Optional[APIClient] = None):
        self.api_client = api_client or APIClient()
        self.session_costs = []

    def log_call(
        self,
        model: str,
        tokens: int,
        cost: float,
        provider: str = "openai",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Manually log an LLM API call.

        Args:
            model: Model name (e.g., 'gpt-4', 'claude-3-opus')
            tokens: Total tokens used
            cost: Cost in USD
            provider: API provider (openai, anthropic, etc.)
            metadata: Additional metadata (function name, etc.)

        Returns:
            Logged entry
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "tokens": tokens,
            "cost": cost,
            "provider": provider,
            "metadata": metadata or {},
        }

        self.session_costs.append(entry)

        # Send to backend if configured
        config = get_config()
        if config.get("api_key"):
            try:
                self.api_client.log_call(entry)
            except Exception as e:
                print(f"Warning: Failed to send cost log to backend: {e}")

        return entry

    def auto_extract_cost(
        self, response: Dict[str, Any], provider: str = "openai"
    ) -> Dict[str, Any]:
        """
        Auto-extract tokens and cost from API response.

        Args:
            response: API response dict
            provider: API provider

        Returns:
            Extracted {model, tokens, cost}
        """
        if provider == "openai":
            return {
                "model": response.get("model", "unknown"),
                "tokens": response.get("usage", {}).get("total_tokens", 0),
                "cost": self._calculate_openai_cost(
                    response.get("model", ""),
                    response.get("usage", {}).get("prompt_tokens", 0),
                    response.get("usage", {}).get("completion_tokens", 0),
                ),
            }
        elif provider == "anthropic":
            return {
                "model": response.get("model", "unknown"),
                "tokens": response.get("usage", {}).get("output_tokens", 0)
                + response.get("usage", {}).get("input_tokens", 0),
                "cost": self._calculate_anthropic_cost(
                    response.get("model", ""),
                    response.get("usage", {}).get("input_tokens", 0),
                    response.get("usage", {}).get("output_tokens", 0),
                ),
            }
        return {"model": "unknown", "tokens": 0, "cost": 0.0}

    @staticmethod
    def _calculate_openai_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate cost for OpenAI models"""
        pricing = {
            "gpt-4": {"prompt": 0.03, "completion": 0.06},
            "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
            "gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
        }
        model_pricing = pricing.get(model, pricing.get("gpt-3.5-turbo"))
        return (prompt_tokens * model_pricing["prompt"] + 
                completion_tokens * model_pricing["completion"]) / 1000

    @staticmethod
    def _calculate_anthropic_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for Anthropic models"""
        pricing = {
            "claude-3-opus": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
        }
        model_pricing = pricing.get(model, pricing.get("claude-3-haiku"))
        return (input_tokens * model_pricing["input"] + 
                output_tokens * model_pricing["output"]) / 1000

    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary of costs logged in this session"""
        if not self.session_costs:
            return {"total_cost": 0.0, "total_tokens": 0, "calls": 0}

        total_cost = sum(call["cost"] for call in self.session_costs)
        total_tokens = sum(call["tokens"] for call in self.session_costs)

        return {
            "total_cost": round(total_cost, 4),
            "total_tokens": total_tokens,
            "calls": len(self.session_costs),
            "by_model": self._group_by_model(),
        }

    def _group_by_model(self) -> Dict[str, Dict[str, Any]]:
        """Group costs by model"""
        by_model = {}
        for call in self.session_costs:
            model = call["model"]
            if model not in by_model:
                by_model[model] = {"cost": 0.0, "tokens": 0, "calls": 0}
            by_model[model]["cost"] += call["cost"]
            by_model[model]["tokens"] += call["tokens"]
            by_model[model]["calls"] += 1

        # Round costs
        for model in by_model:
            by_model[model]["cost"] = round(by_model[model]["cost"], 4)

        return by_model


# Global tracker instance
_tracker = CostTracker()


def track_cost(provider: str = "openai"):
    """
    Decorator to track cost of a function that calls LLM APIs.

    Usage:
        @track_cost(provider="openai")
        def my_function():
            response = openai.ChatCompletion.create(...)
            return response

    Args:
        provider: API provider (openai, anthropic, etc.)

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            # If result is an API response dict, auto-extract costs
            if isinstance(result, dict) and "usage" in result:
                costs = _tracker.auto_extract_cost(result, provider)
                _tracker.log_call(
                    model=costs["model"],
                    tokens=costs["tokens"],
                    cost=costs["cost"],
                    provider=provider,
                    metadata={"function": func.__name__},
                )
            return result

        return wrapper

    return decorator


@contextmanager
def track():
    """
    Context manager for tracking costs within a block.

    Usage:
        with llmlab.track():
            response = openai.ChatCompletion.create(...)
            llmlab.log_call("gpt-4", tokens=150, cost=0.003)

    Yields:
        None
    """
    yield _tracker


def log_call(
    model: str,
    tokens: int,
    cost: float,
    provider: str = "openai",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Manually log an LLM API call.

    Args:
        model: Model name
        tokens: Total tokens used
        cost: Cost in USD
        provider: API provider
        metadata: Optional metadata
    """
    _tracker.log_call(model, tokens, cost, provider, metadata)


def get_session_summary() -> Dict[str, Any]:
    """Get summary of costs in current session"""
    return _tracker.get_session_summary()
