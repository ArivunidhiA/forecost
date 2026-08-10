# Tested product journeys

These journeys are designed for the built wheel and require no API key,
network, account, transcript, or existing Forecost home.

## Five-minute synthetic receipt

```bash
python -m venv .venv
.venv/bin/python -m pip install forecost-0.3.0-py3-none-any.whl
.venv/bin/forecost --help
.venv/bin/forecost lab demo --ledger-path /tmp/forecost-demo.db
```

The final command must print a content-free run ID, evidence state, lifecycle,
causal timing, authority-separated integer-micros totals, and receipt digest.
Running it again with the same seed against a fresh ledger must produce the
same semantic receipt.

## Offline independent evidence

Create a synthetic export; never substitute a private production export in a
bug report:

```json
[
  {
    "timestamp": "2026-01-01T00:00:20Z",
    "amount_micros": 121000,
    "line_item": "model_inference"
  }
]
```

```bash
FORECOST_HOME=/tmp/forecost-history forecost lab demo \
  --ledger-path /tmp/forecost-history/ledger.db
FORECOST_HOME=/tmp/forecost-history forecost reconcile import \
  --source openai --file synthetic-export.json --run RUN_ID
FORECOST_HOME=/tmp/forecost-history forecost reconcile run \
  --run RUN_ID --json-output
FORECOST_HOME=/tmp/forecost-history forecost receipt RUN_ID --markdown
```

The reconciliation must state source coverage, finality, residual, exact versus
aggregate evidence, and unmatched counts. It must never call an aggregate
constraint an exact event match.

## Fake graph-runtime import

```bash
FORECOST_HOME=/tmp/forecost-otel forecost import otel --file synthetic-otel.jsonl
FORECOST_HOME=/tmp/forecost-otel forecost runs list
FORECOST_HOME=/tmp/forecost-otel forecost receipt RUN_ID --json-output
```

The fixture may contain content-shaped sentinel fields; the adapter must ignore
them. Only causal identity, reviewed operation/lifecycle fields, metrics, and
approved dimensions may persist.

## Claude isolated configuration

```bash
forecost setup claude --dry-run --config-dir /tmp/fake-claude
forecost setup claude --apply --config-dir /tmp/fake-claude
forecost setup claude --check --config-dir /tmp/fake-claude
forecost self-test claude
forecost setup claude --uninstall --config-dir /tmp/fake-claude
```

This journey changes only the fake configuration directory. A successful
self-test proves the packaged launcher and synthetic lifecycle path, not live
provider-side containment.
