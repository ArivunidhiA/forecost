"""Validated, machine-refreshed pricing overlay.

``forecost/data/pricing.json`` ships in the wheel and is regenerated on a schedule by
``scripts/update_pricing.py`` (see .github/workflows/pricing-refresh.yml). Users can opt in to
``forecost pricing-update`` which stores a newer copy in ``$FORECOST_HOME/pricing.json``.
The runtime itself never touches the network. Files are untrusted input: bounded size,
strict schema, finite non-negative rates, bounded identifiers.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TypedDict

SCHEMA = 1
MAX_BYTES = 2_000_000
MAX_MODELS = 5_000
MAX_RATE_PER_MTOK = 10_000.0
STALE_AFTER_DAYS = 60
BUNDLED_PATH = Path(__file__).parent / "data" / "pricing.json"
LOCAL_NAME = "pricing.json"
_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RATE_KEYS = ("input", "output", "cache_read", "cache_write")


class PricingDataError(ValueError):
    """The pricing data file is malformed or unsafe."""


class PricingDoc(TypedDict):
    schema: int
    generated_at: str
    source: str
    models: dict[str, dict[str, float]]


def _validate_rate(key: object, value: object) -> float:
    if key not in _RATE_KEYS:
        raise PricingDataError(f"unknown rate key: {key}")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PricingDataError("rates must be numbers")
    if not math.isfinite(value) or value < 0 or value > MAX_RATE_PER_MTOK:
        raise PricingDataError("rate out of range")
    return float(value)


def _validate_model(model: object, rates: object) -> dict[str, float]:
    if not isinstance(model, str) or not _MODEL_ID.match(model) or not isinstance(rates, dict):
        raise PricingDataError("invalid model entry")
    row = {key: _validate_rate(key, value) for key, value in rates.items()}
    if "input" not in row or "output" not in row:
        raise PricingDataError("input and output rates are required")
    return row


def validate(raw: object) -> PricingDoc:
    """Return a normalized copy of ``raw`` or raise :class:`PricingDataError`."""
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise PricingDataError("unsupported pricing data schema")
    generated = str(raw.get("generated_at"))
    try:
        date.fromisoformat(generated)
    except ValueError as error:
        raise PricingDataError("generated_at must be an ISO date") from error
    models = raw.get("models")
    if not isinstance(models, dict) or len(models) > MAX_MODELS:
        raise PricingDataError("models must be a bounded object")
    return {
        "schema": SCHEMA,
        "generated_at": generated,
        "source": str(raw.get("source", ""))[:200],
        "models": {model: _validate_model(model, rates) for model, rates in models.items()},
    }


def read_file(path: Path) -> PricingDoc | None:
    """Load and validate a pricing file; ``None`` when absent or invalid (fail safe)."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        return validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def load_effective() -> tuple[dict[str, dict[str, float]], str | None]:
    """Return (model -> rates, newest generated_at) from bundled data plus a newer local copy."""
    bundled = read_file(BUNDLED_PATH)
    merged: dict[str, dict[str, float]] = dict(bundled["models"]) if bundled else {}
    stamp = bundled["generated_at"] if bundled else None
    try:
        from forecost.core.paths import forecost_home

        local = read_file(forecost_home() / LOCAL_NAME)
    except OSError:
        local = None
    if local and (stamp is None or local["generated_at"] >= stamp):
        merged.update(local["models"])
        stamp = local["generated_at"]
    return merged, stamp


def age_days(stamp: str | None, today: date | None = None) -> int | None:
    if stamp is None:
        return None
    return ((today or datetime.now(timezone.utc).date()) - date.fromisoformat(stamp)).days


def is_stale(stamp: str | None, today: date | None = None) -> bool:
    age = age_days(stamp, today)
    return age is None or age > STALE_AFTER_DAYS
