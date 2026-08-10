# Forecost architecture tour

Forecost is a local evidence system with one central rule: observations are not
conclusions. A runtime token count, a gateway estimate, a public list-rate
valuation, and an imported provider-billed amount may describe the same work,
but they remain separate until an explicit reconciliation states what matched
and what did not.

## Current data flow

```text
runtime/export fixture
        |
        v
content-free adapter contract
        |
        v
append-only observation journal -----> deterministic projection rebuild
        |                                      |
        v                                      v
causal spans + meter facts + charges     recovery/integrity verification
        |                                      |
        +------------------+-------------------+
                           v
                 receipt / reconciliation
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
- `span_id`: one causal operation.
- `parent_span_id` and links: tree ancestry and fan-in dependencies.
- `source_sequence` plus idempotency key: producer replay boundary.
- attempt, branch, checkpoint, agent, and workflow-node identity: structural
  causality without prompt or tool content.

## Economic model

`meter_facts` contain quantities such as token or call counts. `charges` are
valuations with currency, authority, line item, tariff provenance, finality,
and optional supersession. Canonical totals choose one charge per economic
fact and line; they never sum competing authorities as extra consumption.

Authority is explicit: provider billed, provider estimate, gateway estimate,
list-rate equivalent, contract allocation, subscription quota, or unknown.
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

This protects content at rest. It does not protect a ledger from the same local
user deliberately changing their own files, and causal metadata can still
reveal work patterns. The data root therefore remains private local state.

## Recovery and integrity

Journal insertion, projection, and resource transitions are transactional.
Producer/idempotency collisions with different material are rejected. The
journal integrity chain and receipt snapshot digests classify deterministic
mutation states; neither is a signature or remote attestation.

Schema changes use a forward-only `PRAGMA user_version` ladder. A real upgrade
must be dry-run, backed up, restore-tested, and conservative about legacy
identity, finality, and authority.

## Extension rule

An adapter is supported only after it passes the conformance protocol for
identity, duplicates, late events, privacy, crash behavior, finality, and a
public receipt. Optional SDKs must not import on the base-wheel startup path.
No adapter may invent a new economic authority or silently strengthen a
containment claim.

The authoritative product laws are in [`product-contract.md`](product-contract.md),
and the field inventory is in [`data-inventory.md`](data-inventory.md).
