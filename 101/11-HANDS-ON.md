# Hands-on product walkthrough

This walkthrough uses synthetic or temporary data. It requires no API key,
account, network call, transcript, or existing Forecost home.

## 1. See the product boundary

```bash
forecost --help
```

Notice that each current command declares its store boundary. Legacy commands
appear only under `forecost legacy`.

## 2. Generate a deterministic graph receipt

```bash
export FORECOST_HOME="$(mktemp -d)"
forecost lab demo --ledger-path "$FORECOST_HOME/ledger.db"
```

The output should include a synthetic run ID, explicit/unknown causal timing,
authority-separated totals and valuation groups, named evidence profiles, and a
receipt digest. Copy that exact ID and replace the
placeholder below; do not type the literal text `RUN_ID`:

```bash
forecost runs list
forecost receipt <RUN_ID_FROM_DEMO> --markdown
```

Use each command's `--help` if option placement differs. The important lesson
is that the receipt is a view of evidence in one explicit ledger, not a hidden
cloud object.

## 3. Explore failure-shaped topology

```bash
forecost lab chaos
```

This deterministic fixture exercises fan-out, cancellation, or incomplete
lifecycle shapes. Compare it with the simple demo and look for branches,
attempts, waits, evidence gaps, and finality.

## 4. See why two totals are not an experiment

Create two synthetic runs in the same isolated ledger, copy their run IDs, and
ask for a diagnostic comparison:

```bash
export FORECOST_HOME="$(mktemp -d)"
forecost lab demo --ledger-path "$FORECOST_HOME/ledger.db"
forecost lab chaos --ledger-path "$FORECOST_HOME/ledger.db"
forecost compare <FIRST_RUN_ID> <SECOND_RUN_ID> \
  --profile economic-outcome \
  --markdown
```

The command may show an observed list-rate delta if the tariff evidence is
compatible, but the decision must be `ABSTAIN` with
`COMPARISON_MANIFEST_REQUIRED`. This is the intended lesson: two receipts do not
prove the same case, assignment, configuration, evaluator, or outcome source.

Do not fabricate 30 manifest pairs merely to obtain a pass. Full matched mode is
for a predeclared experiment and is specified in the
[comparison contract](../docs/comparison.md); the real field gate remains open.

## 5. Import a declared local economic claim

Create `synthetic-export.json` containing only synthetic data:

```json
[
  {
    "timestamp": "2026-01-01T00:00:20Z",
    "amount_micros": 121000,
    "line_item": "model_inference"
  }
]
```

Then run an isolated reconciliation:

```bash
export FORECOST_HOME="$(mktemp -d)"
forecost lab demo --ledger-path "$FORECOST_HOME/ledger.db"
# Copy the new run ID printed above and substitute it in all three commands.
forecost reconcile import --source openai --file synthetic-export.json --run <RUN_ID_FROM_NEW_DEMO>
forecost reconcile run --run <RUN_ID_FROM_NEW_DEMO> --json-output
forecost receipt <RUN_ID_FROM_NEW_DEMO> --markdown
```

Inspect source coverage, authority, residual, exact versus aggregate evidence,
unmatched counts, and finality. The imported amount should remain distinct from
the local list-rate valuation. This synthetic file is not authenticated provider
evidence. It is stored as `user_imported_claim` regardless of the selected
source name and cannot satisfy the provider-billed evidence profile.

## 6. Try an offline causal import

Create a two-line `synthetic-otel.jsonl` fixture:

```jsonl
{"kind":"span","conversation_id":"conversation-101","trace_id":"0123456789abcdef0123456789abcdef","run_id":"run-101","span_id":"0123456789abcdef","idempotency_key":"event-101","source_sequence":1,"operation_kind":"model","lifecycle":"completed","occurred_at":"2026-01-01T00:00:00Z"}
{"kind":"metric","conversation_id":"conversation-101","trace_id":"0123456789abcdef0123456789abcdef","run_id":"run-101","span_id":"0123456789abcdef","idempotency_key":"meter-101","source_sequence":2,"meter_name":"tokens.input","quantity_micros":4000000,"finality":"final","occurred_at":"2026-01-01T00:00:01Z"}
```

Then import it. Copy the normalized run ID printed by `runs list` before asking
for the receipt:

```bash
export FORECOST_HOME="$(mktemp -d)"
forecost import otel --file synthetic-otel.jsonl
forecost runs list
forecost receipt <RUN_ID_FROM_RUNS_LIST> --json-output
```

A fixture may contain sentinel content fields to prove the adapter ignores
them, but never use a real transcript in a bug report. Receipt v2 has no global
`evidence=complete` claim. Inspect its named structural, economic-estimate,
provider-billed, outcome, and CI profiles: each shows a declared denominator,
satisfied/unmet obligations, freshness, contradiction, and reason codes. The
provider-billed profile remains partial because no authenticated settlement is
present. Because the example provides only occurrence timestamps—not explicit
span intervals—aggregate timing should be unknown rather than invented from
observation latency.

## 7. Inspect health without installing a real integration

```bash
forecost doctor
forecost ledger status
forecost pricing-audit
forecost calibration
```

`doctor` is non-destructive but can initialize the canonical database when it
opens a fresh Forecost home. Use a temporary `FORECOST_HOME` when you need
strict isolation.

## 8. Exercise Claude setup against a fake directory

```bash
CLAUDE_TEST_DIR="$(mktemp -d)"
forecost setup claude --dry-run --config-dir "$CLAUDE_TEST_DIR"
forecost setup claude --apply --config-dir "$CLAUDE_TEST_DIR"
forecost setup claude --check --config-dir "$CLAUDE_TEST_DIR"
forecost self-test claude
forecost setup claude --uninstall --config-dir "$CLAUDE_TEST_DIR"
```

This proves configuration and the synthetic lifecycle path, not live provider
observation or containment. The checked-in source plugin's exact-path launcher
and disabled bootstrap remove its former runtime-resolution path, but no
supported production installer exists while the release hold is active.

## 9. Understand the parallel lanes

After the walkthrough, revisit [How it works](06-HOW-IT-WORKS.md). Manual Claude
usage ingestion, LiteLLM usage, and offline causal import do not all populate
the same tables. When adding a feature, decide explicitly which lane it reads
or writes and what public artifact proves the behavior.
