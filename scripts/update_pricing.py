"""Refresh forecost/data/pricing.json from a public price feed, with safety gates.

Usage:  python scripts/update_pricing.py [--source URL_OR_PATH] [--out PATH] [--today YYYY-MM-DD]

Default source is the community-maintained LiteLLM price table (key-less, public, no user data
sent). Only simple per-token chat models from Anthropic, OpenAI and Gemini are taken. Context-tiered
models are skipped (the table cannot represent them). A rate that moves more than 4x against the
previously known value is NOT applied and is reported for human review. Output is deterministic.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forecost import pricing_data  # noqa: E402
from forecost.pricing import FALLBACK_PRICING  # noqa: E402

DEFAULT_SOURCE = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)
MAX_CHANGE_FACTOR = 4.0
PROVIDERS = {"anthropic", "openai", "gemini"}
TIER_MARKER = "_above_"  # e.g. input_cost_per_token_above_200k_tokens


def load_source(source: str) -> dict[str, dict]:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=60) as response:  # noqa: S310  # nosec B310
            payload = response.read(30_000_000)
    else:
        payload = Path(source).read_bytes()
    data = json.loads(payload)
    if not isinstance(data, dict) or len(data) < 100:
        raise SystemExit("source does not look like a price table; refusing to update")
    return data


def _per_mtok(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return round(float(value) * 1_000_000, 6)


def extract(source: dict[str, dict]) -> dict[str, dict[str, float]]:
    rows: dict[str, dict[str, float]] = {}
    for raw_id, entry in source.items():
        if not isinstance(entry, dict) or entry.get("mode") != "chat":
            continue
        provider = entry.get("litellm_provider")
        if provider not in PROVIDERS:
            continue
        model = raw_id.removeprefix("gemini/")
        if "/" in model or model.startswith("ft:") or not pricing_data._MODEL_ID.match(model):
            continue
        if any(TIER_MARKER in key and entry[key] for key in entry):
            continue  # context/service-tiered: not representable, keep baseline
        rates = {
            "input": _per_mtok(entry.get("input_cost_per_token")),
            "output": _per_mtok(entry.get("output_cost_per_token")),
            "cache_read": _per_mtok(entry.get("cache_read_input_token_cost")),
            "cache_write": _per_mtok(entry.get("cache_creation_input_token_cost")),
        }
        if rates["input"] is None or rates["output"] is None:
            continue
        rows[model] = {k: v for k, v in rates.items() if v is not None}
    return rows


def gate(
    new: dict[str, dict[str, float]], known: dict[str, dict[str, float]]
) -> tuple[dict[str, dict[str, float]], list[str]]:
    accepted: dict[str, dict[str, float]] = {}
    held: list[str] = []
    for model, rates in sorted(new.items()):
        old = known.get(model)
        if old:
            for key in ("input", "output"):
                before, after = old.get(key), rates[key]
                if (
                    before
                    and after
                    and not (1 / MAX_CHANGE_FACTOR <= after / before <= MAX_CHANGE_FACTOR)
                ):
                    held.append(f"{model}.{key}: {before} -> {after}")
                    break
            else:
                accepted[model] = rates
            continue
        accepted[model] = rates
    return accepted, held


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--out", default=str(pricing_data.BUNDLED_PATH))
    parser.add_argument("--today", default=date.today().isoformat())
    args = parser.parse_args()

    known = {k: dict(v) for k, v in FALLBACK_PRICING.items()}
    previous = pricing_data.read_file(Path(args.out))
    if previous:
        known.update(previous["models"])
    accepted, held = gate(extract(load_source(args.source)), known)
    if len(accepted) < 50:
        raise SystemExit(f"only {len(accepted)} usable models extracted; refusing to update")
    document = {
        "schema": pricing_data.SCHEMA,
        "generated_at": args.today,
        "source": args.source if args.source.startswith("http") else "local-file",
        "models": accepted,
    }
    pricing_data.validate(document)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(accepted)} models to {out}")  # noqa: T201
    for line in held:
        print(f"HELD FOR REVIEW (>{MAX_CHANGE_FACTOR}x change): {line}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
