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
MAX_TIERS = 4
MAX_TIER_THRESHOLD = 10_000_000
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
    tiers: dict[str, list[dict[str, float]]]


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


def _validate_tier(model: str, tier: object) -> dict[str, float]:
    if not isinstance(tier, dict) or "above" not in tier:
        raise PricingDataError("tier needs an 'above' threshold")
    above = tier["above"]
    if isinstance(above, bool) or not isinstance(above, int):
        raise PricingDataError("tier threshold must be an integer")
    if not 0 < above <= MAX_TIER_THRESHOLD:
        raise PricingDataError("tier threshold out of range")
    row = _validate_model(model, {k: v for k, v in tier.items() if k != "above"})
    return {"above": float(above), **row}


def _validate_tiers(model: object, tiers: object) -> list[dict[str, float]]:
    if not isinstance(model, str) or not _MODEL_ID.match(model):
        raise PricingDataError("invalid tier model")
    if not isinstance(tiers, list) or not 0 < len(tiers) <= MAX_TIERS:
        raise PricingDataError("tiers must be a short list")
    out = [_validate_tier(model, tier) for tier in tiers]
    thresholds = [t["above"] for t in out]
    if thresholds != sorted(set(thresholds)):
        raise PricingDataError("tier thresholds must be strictly ascending")
    return out


def _bounded_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or len(value) > MAX_MODELS:
        raise PricingDataError(f"{name} must be a bounded object")
    return value


def _validate_header(raw: object) -> str:
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise PricingDataError("unsupported pricing data schema")
    generated = str(raw.get("generated_at"))
    try:
        date.fromisoformat(generated)
    except ValueError as error:
        raise PricingDataError("generated_at must be an ISO date") from error
    return generated


def validate(raw: object) -> PricingDoc:
    """Return a normalized copy of ``raw`` or raise :class:`PricingDataError`."""
    generated = _validate_header(raw)
    assert isinstance(raw, dict)  # noqa: S101 - narrowed by _validate_header
    models = _bounded_object(raw.get("models"), "models")
    tiers = _bounded_object(raw.get("tiers", {}), "tiers")
    return {
        "schema": SCHEMA,
        "generated_at": generated,
        "source": str(raw.get("source", ""))[:200],
        "models": {model: _validate_model(model, rates) for model, rates in models.items()},
        "tiers": {model: _validate_tiers(model, rows) for model, rows in tiers.items()},
    }


def read_file(path: Path) -> PricingDoc | None:
    """Load and validate a pricing file; ``None`` when absent or invalid (fail safe)."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        return validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def load_effective_full() -> tuple[
    dict[str, dict[str, float]], dict[str, list[dict[str, float]]], str | None
]:
    """Return (rates, context tiers, newest generated_at): bundled data plus a newer local copy."""
    bundled = read_file(BUNDLED_PATH)
    rates: dict[str, dict[str, float]] = dict(bundled["models"]) if bundled else {}
    tiers: dict[str, list[dict[str, float]]] = dict(bundled["tiers"]) if bundled else {}
    stamp = bundled["generated_at"] if bundled else None
    try:
        from forecost.core.paths import forecost_home

        local = read_file(forecost_home() / LOCAL_NAME)
    except OSError:
        local = None
    if local and (stamp is None or local["generated_at"] >= stamp):
        rates.update(local["models"])
        tiers.update(local["tiers"])
        stamp = local["generated_at"]
    return rates, tiers, stamp


def load_effective() -> tuple[dict[str, dict[str, float]], str | None]:
    """Return (model -> rates, newest generated_at)."""
    rates, _, stamp = load_effective_full()
    return rates, stamp


def age_days(stamp: str | None, today: date | None = None) -> int | None:
    if stamp is None:
        return None
    return ((today or datetime.now(timezone.utc).date()) - date.fromisoformat(stamp)).days


def is_stale(stamp: str | None, today: date | None = None) -> bool:
    age = age_days(stamp, today)
    return age is None or age > STALE_AFTER_DAYS
