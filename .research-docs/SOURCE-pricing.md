# Core Source: forecost/pricing.py

Self-correcting pricing module with 80+ models and zero external dependencies.

```python
"""Self-correcting pricing module with zero external dependencies."""

import os
import re
from typing import Optional

__all__ = [
    "calculate_cost",
    "get_provider",
    "FALLBACK_PRICING",
    "DEFAULT_COST",
    "MODEL_TIERS",
    "get_tier",
]

# Last verified: March 2026
FALLBACK_PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-2024-11-20": {"input": 2.50, "output": 10.00},
    "gpt-4o-2024-08-06": {"input": 2.50, "output": 10.00},
    "gpt-4o-2024-05-13": {"input": 5.00, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o-mini-2024-07-18": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4-turbo-2024-04-09": {"input": 10.00, "output": 30.00},
    "gpt-4-turbo-preview": {"input": 10.00, "output": 30.00},
    "gpt-4-1106-preview": {"input": 10.00, "output": 30.00},
    "gpt-4-0125-preview": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-4-0613": {"input": 30.00, "output": 60.00},
    "gpt-4-32k": {"input": 60.00, "output": 120.00},
    "gpt-4-32k-0613": {"input": 60.00, "output": 120.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gpt-3.5-turbo-0125": {"input": 0.50, "output": 1.50},
    "gpt-3.5-turbo-1106": {"input": 1.00, "output": 2.00},
    "gpt-3.5-turbo-instruct": {"input": 1.50, "output": 2.00},
    "o1": {"input": 15.00, "output": 60.00},
    "o1-2024-12-17": {"input": 15.00, "output": 60.00},
    "o1-preview": {"input": 15.00, "output": 60.00},
    "o1-preview-2024-09-12": {"input": 15.00, "output": 60.00},
    "o1-mini": {"input": 3.00, "output": 12.00},
    "o1-mini-2024-09-12": {"input": 3.00, "output": 12.00},
    "o3-mini": {"input": 1.10, "output": 4.40},
    "o3-mini-2025-01-31": {"input": 1.10, "output": 4.40},
    "text-embedding-3-small": {"input": 0.02, "output": 0.00},
    "text-embedding-3-large": {"input": 0.13, "output": 0.00},
    "text-embedding-ada-002": {"input": 0.10, "output": 0.00},
    # Anthropic
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-latest": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20240620": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-5-haiku-latest": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-opus-latest": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "claude-2.1": {"input": 8.00, "output": 24.00},
    "claude-2.0": {"input": 8.00, "output": 24.00},
    "claude-instant-1.2": {"input": 0.80, "output": 2.40},
    # Google
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-001": {"input": 0.10, "output": 0.40},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-pro-002": {"input": 1.25, "output": 5.00},
    "gemini-1.5-pro-001": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-flash-002": {"input": 0.075, "output": 0.30},
    "gemini-1.5-flash-001": {"input": 0.075, "output": 0.30},
    "gemini-1.5-flash-8b": {"input": 0.0375, "output": 0.15},
    "gemini-1.5-flash-8b-001": {"input": 0.0375, "output": 0.15},
    "gemini-1.0-pro": {"input": 0.50, "output": 1.50},
    "gemini-pro": {"input": 0.50, "output": 1.50},
    "text-embedding-004": {"input": 0.00, "output": 0.00},
    # Mistral
    "mistral-large-latest": {"input": 2.00, "output": 6.00},
    "mistral-medium-latest": {"input": 2.70, "output": 8.10},
    "mistral-small-latest": {"input": 0.20, "output": 0.60},
    "open-mistral-nemo": {"input": 0.15, "output": 0.15},
    "codestral-latest": {"input": 0.20, "output": 0.60},
    # OpenAI - newer models
    "gpt-4.5-preview": {"input": 75.00, "output": 150.00},
    "o3": {"input": 10.00, "output": 40.00},
    "o3-2025-04-16": {"input": 10.00, "output": 40.00},
    "o3-pro": {"input": 20.00, "output": 80.00},
    "gpt-4o-audio-preview": {"input": 2.50, "output": 10.00},
    "gpt-4o-realtime": {"input": 5.00, "output": 20.00},
    # Anthropic - Claude 4 family
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    # Google Gemini 2.5
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-pro-preview-05-06": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-flash-preview-04-17": {"input": 0.15, "output": 0.60},
    # DeepSeek
    "deepseek-chat": {"input": 0.27, "output": 1.10},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    # xAI
    "grok-2": {"input": 2.00, "output": 10.00},
    "grok-2-mini": {"input": 0.30, "output": 0.50},
    "grok-3": {"input": 3.00, "output": 15.00},
    # Meta (via inference providers)
    "llama-3.1-405b": {"input": 3.00, "output": 3.00},
    "llama-3.1-70b": {"input": 0.80, "output": 0.80},
    "llama-3.3-70b": {"input": 0.80, "output": 0.80},
    # Cohere
    "command-r-plus": {"input": 2.50, "output": 10.00},
    "command-r": {"input": 0.15, "output": 0.60},
}

DEFAULT_COST = {"input": 5.0, "output": 15.0}

MODEL_TIERS: dict[str, list[str]] = {
    "Tier 1 (Heavy)": [
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-4.5-preview",
        "o1",
        "o1-preview",
        "o3",
        "o3-pro",
        "claude-3-5-sonnet-latest",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-20240620",
        "claude-3-opus-20240229",
        "claude-3-opus-latest",
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "gemini-2.5-pro",
        "gemini-1.5-pro",
        "grok-3",
        "mistral-large-latest",
        "llama-3.1-405b",
        "deepseek-reasoner",
    ],
    "Tier 2 (Standard)": [
        "gpt-4o-mini",
        "o1-mini",
        "o3-mini",
        "claude-3-5-haiku-latest",
        "claude-3-5-haiku-20241022",
        "claude-haiku-4-5-20251001",
        "claude-3-sonnet-20240229",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "grok-2",
        "mistral-medium-latest",
        "llama-3.1-70b",
        "llama-3.3-70b",
        "deepseek-chat",
        "command-r-plus",
    ],
    "Tier 3 (Economy)": [
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-instruct",
        "claude-3-haiku-20240307",
        "claude-2.1",
        "claude-2.0",
        "claude-instant-1.2",
        "gemini-1.5-flash-8b",
        "gemini-1.0-pro",
        "gemini-pro",
        "grok-2-mini",
        "mistral-small-latest",
        "open-mistral-nemo",
        "codestral-latest",
        "command-r",
    ],
}

_DATE_SUFFIX_RE = re.compile(r"-\d{4}(-\d{2}-\d{2}|\d{4})?$")


def _log_unknown_model(model: str) -> None:
    log_dir = os.path.expanduser("~/.forecost")
    log_path = os.path.join(log_dir, "error.log")
    try:
        os.makedirs(log_dir, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"[pricing] unknown model: {model}\n")
    except OSError:
        pass


def _resolve_model(model: str) -> Optional[dict[str, float]]:
    if model in FALLBACK_PRICING:
        return FALLBACK_PRICING[model]
    stripped = _DATE_SUFFIX_RE.sub("", model)
    if stripped in FALLBACK_PRICING:
        return FALLBACK_PRICING[stripped]
    while "-" in stripped:
        stripped = stripped.rsplit("-", 1)[0]
        if stripped in FALLBACK_PRICING:
            return FALLBACK_PRICING[stripped]
    return None


def calculate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    cost = _resolve_model(model)
    if cost is None:
        _log_unknown_model(model)
        cost = DEFAULT_COST
    input_cost = (tokens_in / 1_000_000) * cost["input"]
    output_cost = (tokens_out / 1_000_000) * cost["output"]
    return input_cost + output_cost


def get_tier(model: str) -> str:
    """Return the capability tier for a model, e.g. 'Tier 1 (Heavy)'."""
    for tier, models in MODEL_TIERS.items():
        if model in models:
            return tier
    stripped = _DATE_SUFFIX_RE.sub("", model)
    for tier, models in MODEL_TIERS.items():
        if stripped in models:
            return tier
    return "Unknown"


def get_provider(model: str) -> str:
    m = model.lower()
    if "text-embedding-004" in m:
        return "google"
    if m.startswith("gpt-") or m.startswith("o1") or m.startswith("o3") or "text-embedding" in m:
        return "openai"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gemini"):
        return "google"
    if m.startswith("mistral") or m.startswith("codestral") or m.startswith("open-mistral"):
        return "mistral"
    if m.startswith("deepseek"):
        return "deepseek"
    if m.startswith("grok"):
        return "xai"
    if m.startswith("llama"):
        return "meta"
    if m.startswith("command"):
        return "cohere"
    return "unknown"
```

---

## Key Algorithms

### Model Resolution Cascade

```
1. Exact match in FALLBACK_PRICING
2. Strip date suffix (e.g., "gpt-4o-2024-11-20" → "gpt-4o")
3. Progressive prefix stripping (right-to-left on hyphens)
4. Return None → use DEFAULT_COST and log warning
```

**Example:**
- Input: `"gpt-4o-2024-11-20"`
- Step 1: No exact match
- Step 2: Strip date → `"gpt-4o"` → Match!

### Cost Calculation

```
cost = (tokens_in / 1_000_000) * input_price_per_million +
       (tokens_out / 1_000_000) * output_price_per_million
```

Prices are in USD per 1 million tokens.

### Provider Detection

Uses lowercase prefix matching on model names:
- `gpt-`, `o1`, `o3`, `text-embedding` → openai
- `claude` → anthropic
- `gemini`, `text-embedding-004` → google
- `mistral`, `codestral` → mistral
- `deepseek` → deepseek
- `grok` → xai
- `llama` → meta
- `command` → cohere
