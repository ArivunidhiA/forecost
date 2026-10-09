# Forecost architecture tour

Forecost is a local evidence system with one central rule: observations are not
conclusions. A runtime token count, a gateway estimate, a public list-rate
valuation, and an authenticated provider-billed amount (or an unauthenticated
user-imported claim) may describe the same work,
but they remain separate until an explicit reconciliation states what matched
and what did not.

## Current data flow

```text
runtime/export fixture
        |
        v
content-minimizing intended adapter contract
        |
        v
append-only observation journal -----> deterministic projection rebuild
        |                                      |
        v                                      v
causal spans + meter facts + charges     recovery/integrity verification
        |                                      |
        +------------------+-------------------+
                           v
              receipt / reconciliation / compare
                           |
                 text / JSON / Markdown
```

Resource envelopes use the same local SQLite transaction boundary but are not
provider-side controls. Claude hooks and gateway callbacks describe their exact
observation or containment boundary; a missing hook is visible and fail-open.

## Identity hierarchy

- `conversation_id`: continuity across related work.
- `trace_id`: portable distributed trace identity when conforming; otherwise
  an irreversible local identifier.
- `run_id`: one workflow/run receipt boundary.
- `span_id`: one causal operation, unique only inside its trace.
- `span_key`: internal trace-scoped identity used by every projection join.
- `parent_span_key` and trace-scoped links: tree ancestry and fan-in dependencies.
- `source_sequence` plus idempotency key: producer replay boundary.
- attempt, branch, checkpoint, agent, and workflow-node identity: structural
  causality without prompt or tool content.

## Economic model

`meter_facts` contain quantities such as token or call counts. `charges` are
valuations with currency, authority, line item, tariff provenance, finality,
and optional supersession. Canonical totals choose one charge per economic
fact and line; they never sum competing authorities as extra consumption.

Authority is explicit: provider billed, provider estimate, gateway estimate,
user-imported claim, list-rate equivalent, contract allocation, subscription
quota, or unknown. Arbitrary JSON/CSV imports are user-imported claims; the
current CLI has no authenticated profile that can establish billed authority.
Finality is separate from authority. Late evidence creates a new observation
and may supersede an earlier reconciliation; it does not rewrite the journal.

## Storage boundaries

- `ledger.db`: canonical observations, projections, receipts, reconciliation,
  and experimental local resource scopes.
- `costs.db`: retired v0.2 forecast-era compatibility only.
- recovery/queue/hook state: bounded, owner-only operational files under the
  selected Forecost home.
- Run Lab: an explicit temporary or caller-selected ledger that never reads the
  user's Forecost home.

Every public command declares its store boundary in `forecost --help`. A
current command may not silently fall back to the legacy database.

## Privacy boundary

Persistent current-product state permits typed causal topology, bounded
lifecycle codes, quantities, valuations, provenance, finality, outcome codes,
and operational health. It rejects or irreversibly pseudonymizes prompts,
completions, tool inputs/outputs, source code, credentials, raw paths, baggage,
tracestate, and unbounded external identifiers/errors.

The current worktree repairs the known current cursor/error paths, but the
legacy SDK/`costs.db`, pre-hardening upgrade artifacts, and custom state outside
the owned home still prevent an end-to-end content-exclusion claim; see
`docs/status.md`. The contract does not protect a ledger from the same local
user deliberately changing their own files, and causal metadata can still
reveal work patterns. The data root therefore remains private local state.

## Recovery and integrity

Journal insertion, projection, and resource transitions are transactional.
Producer/idempotency collisions with different material are rejected. The
journal integrity chain and receipt snapshot digests classify deterministic
mutation states; neither is a signature or remote attestation.

Canonical connections use WAL with `synchronous=FULL`. Schema changes use a
forward-only `PRAGMA user_version` ladder and SQLite's Backup API, followed by
integrity checks. A real upgrade must be dry-run, backed up, restore-tested, and
conservative about legacy identity, finality, and authority.

Comparison and MCP readers open an existing current-schema database with SQLite
`mode=ro` plus `query_only`; they do not initialize or migrate the ledger or
write Forecost rows. SQLite may nevertheless create or update WAL/SHM
coordination sidecars to form a consistent view. They do not use
`immutable=1`, because that can omit committed pages still present in a live
WAL.

See [ADR 0008](adr/0008-sqlite-durability.md) for the durability boundary and
[ADR 0003](adr/0003-economic-authority.md) for authority rules.

## Matched-cohort comparison

`forecost/comparison.py` does not mutate canonical Forecost rows or schema. It
intentionally has two paths:

- diagnostic comparison accepts two valid existing run IDs, may show a scoped observed delta,
  and always abstains because run shape alone cannot establish workload or
  outcome identity;
- matched-cohort comparison accepts digest-bound baseline/candidate arm
  manifests plus a strict predeclared policy. Version 1 requires an exact roster
  of at least 30 pairs, separate attempts and runs, matching dataset/task/
  verifier/source identity, complete one-to-one list-rate valuation coverage for
  final `delta` meters under matching tariff digests, predeclared deterministic
  test/build outcome evidence, qualified structural/outcome profiles, and
  deterministic confidence bounds.

Both paths validate one WAL-consistent in-memory Backup API copy. They verify the
journal chain, hash the journal-derived projections, rebuild those projections
deterministically in memory, compare the hashes, and read the exact validated
copy. Broken journal, projection drift, or a recognized deterministic rebuild
failure is invalid/exit 4. More than 1,000,000 global journal observations is an
abstention/exit 3. Reconciliation batches are not journal-derived in v1, so any
batch on a candidate run forces `RECONCILIATION_EVIDENCE_UNVERIFIED` abstention.
The deterministic bootstrap seed depends only on a fixed protocol label and
sorted quantitative paired observations, not caller-controlled identifiers.

The result is an observational paired difference. Manifest declarations are
manifest-attested, not authenticated; SHA-256 binds local serialization but is
not a signature. Provider-billed comparison, currency conversion, causal
savings, and live admission/control are outside v1. The normative input,
decision, and exit contract is in [`comparison.md`](comparison.md).

## Extension rule

An adapter is supported only after it passes the conformance protocol for
identity, duplicates, late events, privacy, crash behavior, finality, and a
public receipt. Optional SDKs must not import on the base-wheel startup path.
No adapter may invent a new economic authority or silently strengthen a
containment claim.

The authoritative product laws are in [`product-contract.md`](product-contract.md),
and the field inventory is in [`data-inventory.md`](data-inventory.md).
