# Forecost comparison contract

**Contract status:** experimental implementation under the 2026-08-13 release
hold

**Result schema:** `forecost.compare/1`

**Matched policy:** `forecost.economic-outcome/1`

**Arm manifest:** `forecost.compare-arm/1`

This document is the normative explanation of the narrow comparison prototype.
It does not clear the release hold or the field/demand gate.

## The rule in one sentence

Subtracting two run totals is a diagnostic, not an experiment. Forecost permits
a potentially qualifying comparison only when the caller predeclares and binds
the exact paired workload, configurations, evidence sources, tariffs, receipts,
and predeclared deterministic test/build outcome evidence.

Version 1 reports an **observed paired difference**. It does not establish that
the candidate caused a saving, that a manifest is truthful, that a task is
correct, or that the amounts are provider bills.

## Two modes that must not be confused

### Run-ID diagnostic: always abstains

```bash
forecost compare BASELINE_RUN_ID CANDIDATE_RUN_ID \
  --profile economic-outcome \
  --json-output
```

This read-only mode may show a final authority-specific delta when the two
receipts contain compatible tariff evidence. For two valid existing runs its
decision is always `abstain` with `COMPARISON_MANIFEST_REQUIRED`. A missing or
malformed stored run instead makes the diagnostic `invalid`; it never upgrades
to pass/fail. Run shape and similar totals cannot prove that two attempts had
the same task, evaluator, outcome source, or assignment.

The CLI validates both run IDs and the diagnostic authority/currency/line-item
scope before it opens `ledger.db`. A malformed identifier is therefore a
configuration error (exit 64), not a database lookup or an `unknown run`
decision.

The optional MCP tool `forecost_compare_runs` exposes only this diagnostic mode.
It does not accept cohort manifests, reserve budget, stop loops, write evidence,
or turn an abstention into an assertion.

### Matched-cohort evaluation: strict and predeclared

```bash
forecost compare baseline-arm.json candidate-arm.json \
  --profile economic-outcome \
  --policy economic-outcome-policy.json \
  --json-output
```

Here the first two arguments are arm-manifest paths, not run IDs. The policy owns
the authority, currency, line items, case roster, source denominator, minimum
cohort, thresholds, and confidence configuration. Diagnostic scope flags cannot
override it.

The implementation reads canonical `ledger.db` receipts and does not insert,
update, delete, migrate, or initialize Forecost rows or schema. JSON inputs are
bounded and strict: duplicate keys, floating-point numbers, unexpected fields,
oversized files, malformed identifiers, and invalid digest forms are rejected
as configuration errors before the ledger is opened.

“Read-only” here describes Forecost's logical database behavior, not a promise
that opening a WAL database is a zero-write filesystem operation. The source is
opened with SQLite `mode=ro` and `query_only`; SQLite may create or update
`ledger.db-wal`/`ledger.db-shm` coordination sidecars while establishing a
consistent WAL view. Forecost deliberately does not use `immutable=1`: treating
a live WAL database as immutable can ignore committed pages and return stale or
incomplete evidence.

## Exact v1 input contract

All digest values below are lowercase 64-character SHA-256 hex strings. IDs are
bounded opaque identifiers. The syntax check cannot prove privacy, so callers
must not place prompts, paths, descriptions, or task-content labels in them.
Arrays that the schema treats as sets must be sorted and unique.

### Arm manifest

Both baseline and candidate manifests contain exactly these fields:

| Field | Meaning |
| --- | --- |
| `schema` | Literal `forecost.compare-arm/1` |
| `arm` | Literal `baseline` or `candidate`, matching its position |
| `manifest_digest` | SHA-256 of canonical JSON for the manifest with this field omitted |
| `dataset_digest` | Identity of the frozen dataset/case source |
| `task_set_digest` | Identity of the exact task/version roster |
| `configuration_digest` | Identity of the arm's complete model+harness+policy configuration |
| `privacy_profile` | Must be `metadata_minimized_v1` in comparison v1 |
| `source_ids` | Sorted, unique evidence-source denominator |
| `cases` | Sorted, unique case records; at most 10,000 |

Each case contains exactly:

| Field | Meaning |
| --- | --- |
| `case_id` | Stable case identity used by the policy roster |
| `task_version` | Frozen task version |
| `attempt_id` | One attempt; must not be reused in either arm |
| `pair_id` | Stable pairing identity shared by the two arms |
| `evaluator_id` | Manifest-attested identity of the evaluation procedure |
| `verifier_id` / `verifier_version` | Frozen deterministic verifier identity |
| `outcome_source_id` | Declared source that produced the outcome evidence |
| `outcome_evidence_id` | Exact active test/build evidence row in the run |
| `run_id` | Canonical ledger run; must be unique across both arms |
| `receipt_digest` | Exact local receipt-v2 payload digest expected for this run |
| `tariff_digest` | Canonical digest of the list-rate tariff used by the scoped charges |
| `configuration_digest` | Must equal the enclosing arm configuration digest |

Baseline and candidate must have the same ordered case, pair, task, evaluator,
verifier, and outcome-source roster. Their attempt and run IDs must be distinct.
This guards against comparing a run to itself while pretending it is a repeated
trial.

### Predeclared policy

The policy contains exactly:

| Field | v1 rule |
| --- | --- |
| `schema` | Literal `forecost.economic-outcome/1` |
| `authority` | Literal `list_rate` |
| `currency` | Literal `USD`; no FX conversion |
| `line_items` | Sorted, unique economic lines included in the total |
| `expected_case_ids` | Sorted, unique exact case roster |
| `expected_source_ids` | Sorted, unique source denominator required in both arms |
| `min_pairs` | Integer from 30 through 10,000, not greater than the roster |
| `min_reduction_bps` | Required lower confidence bound for economic reduction, 0–10,000 basis points |
| `max_outcome_regression_bps` | Largest permitted lower-bound outcome regression, 0–10,000 basis points |
| `confidence_bps` | Two-sided confidence level, 5,000–9,999 basis points |
| `bootstrap_samples` | Deterministic paired-bootstrap sample count, 100–100,000; samples × expected pairs must not exceed 5,000,000 draws |
| `baseline_configuration_digest` | Must bind the baseline arm |
| `candidate_configuration_digest` | Must bind the candidate arm |
| `dataset_digest` / `task_set_digest` | Must bind both arms and the predeclared workload |
| `freshness_contract` | Literal `frozen_receipt_snapshot` |
| `claim_mode` | Literal `observational` |

The manifest digest is computed from deterministic canonical JSON: UTF-8,
sorted object keys, compact separators, ASCII escaping, and the
`manifest_digest` member omitted. This is an implementation binding, not an
authentication ceremony. A future protocol publication would need to freeze
canonicalization independently and supply interoperable fixtures before another
implementation should rely on it.

The 30-pair minimum is a conservative product-contract floor, **not a power
analysis**. An experiment owner must justify its dataset, pairing, thresholds,
confidence level, and sample size for the actual decision. Forecost does not
infer statistical adequacy merely because the minimum is met.

## Frozen validation boundary

After the cheap manifest/policy binding checks pass, comparison v1 validates one
frozen database state before it reads any decision evidence:

1. it refuses to scan more than **1,000,000 global journal observations**;
2. it uses SQLite's Backup API to copy the source—including committed pages that
   are still in WAL—into a private in-memory database;
3. it verifies the append-only journal chain and same-database anchor;
4. it hashes the journal-derived identity, run/span, link, meter, charge, and
   outcome projections;
5. it deterministically rebuilds those projections from the journal in the
   in-memory copy, hashes them again, and compares the two states; and
6. it switches that copy to `query_only` and evaluates every pair from the exact
   state that was validated.

The rebuild never touches the source ledger. A broken journal chain,
projection/hash mismatch, or recognized deterministic rebuild failure makes the
evidence `invalid` (exit 4), using `JOURNAL_INTEGRITY_NOT_INTACT`,
`PROJECTION_INTEGRITY_MISMATCH`, or `PROJECTION_REBUILD_FAILED`. Exceeding the
global journal cap instead returns `abstain` (exit 3) with
`PROJECTION_VALIDATION_RESOURCE_LIMIT`; it is a bounded-work refusal, not proof
that the evidence is corrupt. An unexpected SQLite or internal failure remains
exit 5.

## What one pair must prove

A pair qualifies only when all relevant checks succeed after the frozen
validation boundary above succeeds:

1. the declared run exists, is terminal, and rebuilds into a well-formed receipt;
2. the receipt's local SHA-256 payload digest verifies and equals the manifest;
3. the `structural` and `outcome` profiles are complete and contradiction-clear;
4. every predeclared source is present;
5. the selected outcome is one active, decisive `test_exit` or `build_exit`
   record bound to the declared run, evidence ID, and source ID;
6. every meter fact in the receipt uses `aggregation: delta` and
   `finality: final`; the in-scope valuation groups provide complete one-to-one coverage of
   exactly those meter fact IDs, with exactly one `list_rate` alternative per
   group, non-negative integer micros, and a fact/charge binding to the same run;
7. every qualifying charge has a non-empty tariff with a `rate_snapshot`, the
   resulting tariff digest matches the declared case tariff, and baseline and
   candidate tariff scope agrees; and
8. the run has **no** `reconciliation_batches` row.

The last rule is intentionally conservative. Reconciliation batches are useful
local evidence, but they are not currently journal-derived projections covered
by the deterministic rebuild/hash check. Any batch—matching, discrepant, final,
or provisional—therefore forces `abstain` with
`RECONCILIATION_EVIDENCE_UNVERIFIED`; v1 does not selectively trust its mutable
state.

The paired arms must also use the same deterministic outcome evidence type
(`test_exit` or `build_exit`), and its confidence must be `observed` or
`explicit`. A mixed test/build basis or `unknown`/`inferred` confidence causes
abstention.

If evidence is missing, ambiguous, contradictory, reused, or
bound to a different run/source/tariff, Forecost excludes the pair and reports
machine-readable reason codes. It does not impute a value, relax the roster, or
silently change authority.

## Statistics and the meaning of `pass`

For qualified pairs Forecost calculates:

- total baseline and candidate integer USD micros;
- observed economic reduction in basis points relative to the baseline total;
- baseline/candidate counts of decisive good outcomes;
- observed paired outcome difference in basis points; and
- deterministic paired-bootstrap lower and upper bounds for both measures.

The bootstrap seed is derived only from a fixed protocol label plus the sorted
quantitative paired observations (baseline/candidate integer micros and outcome
scores). Caller-chosen case, attempt, run, manifest, and source labels do not
enter the seed, so renaming opaque identifiers cannot grind a finite-bootstrap
decision. The same quantitative observations and implementation produce the
same resampling bounds. This is reproducibility, not a guarantee that the
sampling model is appropriate.

A `pass` means the qualified cohort met the predeclared minimum and both lower
confidence bounds met the declared economic and outcome thresholds. It means
only that the **observed v1 evidence passed this policy**. It does not mean
“proved savings,” “better model,” “correct output,” “provider-billed,” or
“production approved.”

## Result disclosure

The `forecost.compare/1` JSON result keeps the decision inputs visible:

- `scope` records `list_rate`, `USD`, selected line items, and
  `claim_mode: observational`;
- `decision_basis` records the policy digest, minimum, economic/outcome
  thresholds, confidence level, bootstrap count, frozen-snapshot rule, and
  interval method
  `deterministic_sha256_counter_paired_bootstrap`;
- `input_bindings` records both manifest, dataset, task-set, configuration, and
  privacy-profile identities plus the policy-side bindings and expected source
  IDs;
- `matching` records expected, minimum, qualified, and excluded pairs with
  reason codes;
- `evidence.external_declaration_boundary` is explicitly
  `manifest_attested_not_authenticated`; and
- `integrity.payload_digest` binds the result's local deterministic
  serialization without signing it.

Diagnostic results have no matched policy and therefore leave
`decision_basis` null and do not emit matched-cohort `input_bindings`.

## Decisions and process exits

| Decision | Exit | Meaning |
| --- | ---: | --- |
| `pass` | 0 | Qualified evidence met both predeclared lower-bound thresholds |
| `fail` | 2 | Qualified evidence missed an economic or outcome threshold |
| `abstain` | 3 | The requested claim cannot be made from the available/declared evidence, including unverified reconciliation state or the global journal validation cap |
| `invalid` | 4 | Evidence identity, digest, run, binding, journal chain, or journal-derived projection/rebuild state is invalid |
| configuration/usage error | 64 | Input shape or invocation violates the v1 contract |
| internal error | 5 | The comparison could not be evaluated because of an internal/SQLite failure; the library exit mapper also defaults malformed result objects to 5 |

Scripts should branch on the exit code and inspect
`decision.reason_codes`; they should not scrape prose. Text, Markdown, and JSON
are views of the same decision contract.

## Trust and cryptographic boundary

- `manifest_digest`, `receipt_digest`, `input_digest`, and result integrity are
  local SHA-256 consistency bindings. They are not signatures.
- Matched mode copies one WAL-consistent state into memory, verifies the local
  journal chain, and rejects a deterministic projection rebuild/hash mismatch.
  This detects a projection-only edit and several journal rewrite/gap/fork/
  reordering classes. The chain head and projections still share the database's
  trust boundary, so a coordinated same-UID rewrite can replace all of them
  consistently.
- `reconciliation_batches` is outside the journal-derived projection inventory.
  Its mere presence forces abstention instead of inheriting the validated label.
- The arm files attest that a dataset, assignment, evaluator, source, and
  configuration were used. Forecost does not authenticate those declarations.
- A process with the same operating-system UID can replace the database,
  manifests, and digests consistently. That actor is outside the current local
  integrity boundary.
- The bound outcome is predeclared deterministic evidence that a named
  test/build command exited one way. Evaluator/source declarations are
  manifest-attested, not authenticated, and the exit is not semantic proof that
  the agent solved the task.
- Version 1 excludes provider-billed authority, exchange rates, discounts,
  account settlement, causal attribution, and randomized/judgment outcomes.

Do not expose real task content through IDs. Manifests and comparison output are
content-minimizing by field design but still reveal cohort size, timing/economic
structure, source relationships, and stable linkable identifiers.

## Field gate and release status

The comparison engine is an internal product hypothesis, not a validated daily
tool. The release hold remains because the repository still has eight P0
blockers, including legacy raw metadata, out-of-home state, missing authenticated
provider/live validation, missing independent security/privacy review, no full
upgrade sanitizer, legacy public distribution, the unpassed comparison/demand
gate, and the same-UID boundary.

Before broader Lab, mutable MCP, or CI assertion investment, the current master
plan requires at least 30 blinded graph-shaped comparisons, zero false factual
claims on the adversarial collision corpus, a Forecost-only actionable finding
rate of at least 30%, and at least three recurring decision classes. Failure
triggers a protocol/merge/archive decision rather than a broader launch.

See the [current status](status.md) and
[master product checklist](research/2026-08-13-master-product-launch-checklist.md).

## Where Forecost fits

This is a boundary comparison, not a claim that another project cannot add a
feature. Evaluate tools against their current documentation and your own data.

| Tool category | Usually answers | Forecost's different job |
| --- | --- | --- |
| Provider usage or billing export | What one provider reports for an account/window | Preserve that report as one authority; comparison v1 deliberately does not call it authenticated billing |
| Gateway cost dashboard | What passed through one gateway | Retain gateway valuation without treating unseen work or provider adjustments as covered |
| Trace/observability platform | What spans, logs, and payloads describe execution | Produce a portable, content-minimized economic receipt with explicit disclosure and evidence gaps |
| Harness-native evaluator | How candidate configurations score on its tasks | Require exact predeclared outcome identity while keeping economic authority and receipt evidence explicit; evaluator/source declarations remain manifest-attested |
| Local transcript usage viewer | What one local transcript exposes | Explain graph/authority gaps and refuse unmatched subtraction |
| Budget callback or counter | Whether one integration crossed a local threshold | Reconcile post-run graph evidence; the current comparison and MCP surfaces are not live controls |

Forecost is useful only when multiple sources or graph-shaped runs make
provenance, disagreement, retry identity, or missing evidence matter. If one
trustworthy total or an established evaluation harness answers the question, the
simpler tool is the correct baseline.
