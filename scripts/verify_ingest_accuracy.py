"""Independent accuracy check: recount Claude transcripts without Forecost code, compare to the
ledger Forecost produced from the same files. Prints aggregates only (never content).

Usage: python scripts/verify_ingest_accuracy.py CLAUDE_PROJECTS_DIR LEDGER_DB
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

FIELDS = (
    ("input_tokens", "tokens_in"),
    ("output_tokens", "tokens_out"),
    ("cache_read_input_tokens", "tokens_cache_read"),
    ("cache_creation_input_tokens", "tokens_cache_write"),
)


def recount(root: Path) -> tuple[dict[str, dict[str, int]], int, int]:
    """Per API response (requestId; uuid when absent) take the per-field MAXIMUM usage seen.

    Claude Code logs a streamed response as several records whose usage counters grow, so the
    first record is a partial; counters are cumulative, hence max-per-field is the final value.
    """
    best: dict[str, dict[str, int]] = {}
    model_of: dict[str, str] = {}
    lines_bad = 0
    for path in sorted(root.rglob("*.jsonl")):
        with path.open("rb") as handle:
            for raw in handle:
                try:
                    rec = json.loads(raw)
                except ValueError:
                    lines_bad += 1
                    continue
                if not isinstance(rec, dict) or rec.get("type") != "assistant":
                    continue
                message = rec.get("message")
                usage = message.get("usage") if isinstance(message, dict) else None
                if not isinstance(usage, dict):
                    continue
                key = rec.get("requestId") or rec.get("uuid")
                if not key:
                    continue
                model_of.setdefault(key, str(message.get("model") or "unknown"))
                slot = best.setdefault(key, {})
                for source, target in FIELDS:
                    value = usage.get(source)
                    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                        slot[target] = max(slot.get(target, 0), value)
    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    records = 0
    for key, slot in best.items():
        if not slot:
            continue  # no positive token counts: no cost, not an event
        records += 1
        for target, value in slot.items():
            totals[model_of[key]][target] += value
    return totals, records, lines_bad


def ledger_totals(db: Path) -> tuple[dict[str, int], int]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        sums = {
            target: conn.execute(f"SELECT COALESCE(SUM({target}),0) FROM usage_events").fetchone()[
                0
            ]  # noqa: S608
            for _, target in FIELDS
        }
        count = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
    finally:
        conn.close()
    return sums, count


def main(argv: list[str]) -> int:
    root, db = Path(argv[1]), Path(argv[2])
    totals, records, bad = recount(root)
    independent = {t: sum(m[t] for m in totals.values()) for _, t in FIELDS}
    ledger, events = ledger_totals(db)
    sys.stdout.write(
        f"transcripts: {records} unique billable API responses ({bad} unparseable lines)\n"
    )
    sys.stdout.write(f"ledger:      {events} usage events\n")
    ok = events == records
    for _, target in FIELDS:
        a, b = independent[target], ledger[target]
        flag = "OK" if a == b else f"MISMATCH ({b - a:+d})"
        ok = ok and a == b
        sys.stdout.write(f"  {target:20s} independent={a:>16,d} ledger={b:>16,d}  {flag}\n")
    sys.stdout.write("ACCURACY: " + ("EXACT MATCH" if ok else "DIFFERENCES FOUND") + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
