# Tested product journeys

> **Synthetic developer journeys, not release evidence.** The current worktree
> contains internal remediations for the 2026-08-13 receipt/privacy/durability
> findings, but [status](status.md) retains the publication hold. Use only
> synthetic data in a user-owned temporary directory. Success does not prove
> live adapter completeness, authenticated provider origin, same-user tamper
> resistance, external privacy review, or release readiness.

These historical journeys were designed for a built wheel. The ignored `dist/`
artifacts in this workspace are stale and do not match the prior QA digest, so
do not install them. Rebuild from the reviewed source into a clean temporary
directory before rerunning any packaged journey.

## Five-minute synthetic receipt

Run the journey blocks in the same shell so `REVIEW_VENV` remains defined.

```bash
REVIEW_VENV="$(mktemp -d)/venv"
BUILD_DIR="$(mktemp -d)"
python3.12 -m venv "$REVIEW_VENV"
"$REVIEW_VENV/bin/python" -m pip install --upgrade pip build
"$REVIEW_VENV/bin/python" -m build --outdir "$BUILD_DIR"
# Install only the wheel just built from this reviewed source, then record its SHA-256.
shasum -a 256 "$BUILD_DIR/forecost-0.3.0-py3-none-any.whl"
"$REVIEW_VENV/bin/python" -m pip install "$BUILD_DIR/forecost-0.3.0-py3-none-any.whl"
"$REVIEW_VENV/bin/forecost" --help
DEMO_DIR="$(mktemp -d)"
"$REVIEW_VENV/bin/forecost" lab demo --ledger-path "$DEMO_DIR/ledger.db"
```

The final command prints a synthetic run ID, receipt-v2 claim profiles,
lifecycle/outcome, an explicit unknown timing result, selected authority total,
known blind spots, and a local-consistency digest. Running it again with the
same seed against a fresh ledger must produce the same semantic receipt. The
claim profiles have explicit obligations, competing valuations remain grouped
without being summed, and timing is withheld unless complete explicit intervals
exist. This synthetic result is not evidence that a live adapter satisfies the
same profiles.

## Offline declared economic claim

```bash
HISTORY_DIR="$(mktemp -d)"
FIXTURE_DIR="$(mktemp -d)"
EXPORT_FILE="$FIXTURE_DIR/synthetic-export.json"
"$REVIEW_VENV/bin/python" - "$EXPORT_FILE" <<'PY'
import json
import sys
from pathlib import Path

payload = [{
    "timestamp": "2026-01-01T00:00:20Z",
    "amount_micros": 121000,
    "line_item": "model_inference",
}]
Path(sys.argv[1]).write_text(json.dumps(payload), encoding="utf-8")
PY

DEMO_OUTPUT="$(FORECOST_HOME="$HISTORY_DIR" "$REVIEW_VENV/bin/forecost" \
  lab demo --ledger-path "$HISTORY_DIR/ledger.db")"
printf '%s\n' "$DEMO_OUTPUT"
RUN_ID="$(printf '%s\n' "$DEMO_OUTPUT" | sed -n 's/^Run: //p' | head -n 1)"
test -n "$RUN_ID"

FORECOST_HOME="$HISTORY_DIR" "$REVIEW_VENV/bin/forecost" reconcile import \
  --source openai --file "$EXPORT_FILE" --run "$RUN_ID"
FORECOST_HOME="$HISTORY_DIR" "$REVIEW_VENV/bin/forecost" reconcile run \
  --run "$RUN_ID" --json-output
FORECOST_HOME="$HISTORY_DIR" "$REVIEW_VENV/bin/forecost" receipt "$RUN_ID" --markdown
```

The reconciliation must state source coverage, finality, residual, exact versus
aggregate evidence, and unmatched counts. It must never call an aggregate
constraint an exact event match.

## Fake graph-runtime import

```bash
OTEL_DIR="$(mktemp -d)"
OTEL_FIXTURE_DIR="$(mktemp -d)"
OTEL_FILE="$OTEL_FIXTURE_DIR/synthetic-otel.jsonl"
"$REVIEW_VENV/bin/python" - "$OTEL_FILE" <<'PY'
import sys
from pathlib import Path

lines = [
    '{"kind":"span","conversation_id":"golden","trace_id":"0123456789abcdef0123456789abcdef","run_id":"golden-run","span_id":"0123456789abcdef","idempotency_key":"golden-span","source_sequence":1,"operation_kind":"model","lifecycle":"completed","occurred_at":"2026-01-01T00:00:00Z"}',
    '{"kind":"metric","conversation_id":"golden","trace_id":"0123456789abcdef0123456789abcdef","run_id":"golden-run","span_id":"0123456789abcdef","idempotency_key":"golden-meter","source_sequence":2,"meter_name":"tokens.input","quantity_micros":4000000,"finality":"final","occurred_at":"2026-01-01T00:00:01Z"}',
]
Path(sys.argv[1]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

FORECOST_HOME="$OTEL_DIR" "$REVIEW_VENV/bin/forecost" import otel --file "$OTEL_FILE"
RUNS_OUTPUT="$(FORECOST_HOME="$OTEL_DIR" "$REVIEW_VENV/bin/forecost" runs list)"
printf '%s\n' "$RUNS_OUTPUT"
OTEL_RUN_ID="$(printf '%s\n' "$RUNS_OUTPUT" | awk 'NF {print $1; exit}')"
test -n "$OTEL_RUN_ID"
FORECOST_HOME="$OTEL_DIR" "$REVIEW_VENV/bin/forecost" \
  receipt "$OTEL_RUN_ID" --json-output
```

The fixture may contain content-shaped sentinel fields; the adapter must ignore
them. Only causal identity, reviewed operation/lifecycle fields, metrics, and
approved dimensions may persist.

## Claude isolated configuration

```bash
CLAUDE_TEST_DIR="$(mktemp -d)"
"$REVIEW_VENV/bin/forecost" setup claude --dry-run --config-dir "$CLAUDE_TEST_DIR"
"$REVIEW_VENV/bin/forecost" setup claude --apply --config-dir "$CLAUDE_TEST_DIR"
"$REVIEW_VENV/bin/forecost" setup claude --check --config-dir "$CLAUDE_TEST_DIR"
"$REVIEW_VENV/bin/forecost" self-test claude
"$REVIEW_VENV/bin/forecost" setup claude --uninstall --config-dir "$CLAUDE_TEST_DIR"
```

This journey changes only the fake configuration directory. A successful
self-test proves the packaged launcher and synthetic lifecycle path, not live
provider-side containment.
