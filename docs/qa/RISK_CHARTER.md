# Forecost QA risk charter

> **Historical risk charter.** These are hypotheses the 2026-08-09 QA pass
> tried to test, not current guarantees. The 2026-08-13 red team found P0
> violations of items 1–4, 6, 8, and 10 in that baseline; the current worktree
> contains later internal repairs, but not an external release audit. Current truth is in
> [`../status.md`](../status.md).

**Frozen:** 2026-08-09, before broad packaged-product QA.

## Highest-risk assumptions

1. A receipt cannot accidentally merge retries, branches, sessions, or
   independent source facts into one economic claim.
2. Provider/gateway estimates are never promoted to provider-billed authority,
   and competing valuations are never summed as separate consumption.
3. Content-free ingestion remains content-free across normal, malformed,
   exception, recovery, queue, hook, and migration paths.
4. Append-only history and receipt snapshots detect material deletion, rewrite,
   reorder, duplicate, truncation, and fork behavior deterministically.
5. Resource reservations conserve parent ownership under process concurrency,
   retry, lease expiry, crash, and late settlement.
6. Claude and LiteLLM integrations degrade visibly and safely; a missing or stale
   hook cannot be described as containment.
7. The clean installed base wheel has no missing optional dependency or entry
   point and does not import legacy forecasting dependencies on startup.
8. Upgrade paths preserve old evidence and do not silently assign modern
   completeness, identity, or billing authority to ambiguous legacy data.
9. Large ledgers remain bounded enough for local use and do not put analytical
   SQLite work on callback hot paths.
10. Public docs, help, metadata, capability declarations, and actual behavior do
    not contradict one another.

## Adversarial conditions

- Duplicate, late, missing, reordered, malformed, oversized, and conflicting
  source records.
- Fan-out/fan-in, cancellation, checkpoint/resume, replay, retry, and ambiguous
  parent identity.
- Concurrent processes, SQLite busy/full/corrupt states, interrupted commit,
  expired lease, and restart between every state transition.
- Symlink substitution, unsafe modes/ownership, path traversal, malicious local
  project configuration, secret-like identifiers, and sentinel content in every
  external string field.
- Empty history, stale watermark, partially installed optional extras, copied
  environment, source checkout absent, and read-only data root.

## Evidence standard

Critical claims require all three layers where applicable:

1. **Interface evidence:** the real installed CLI or adapter entry point.
2. **State evidence:** durable ledger/filesystem state and invariants.
3. **Oracle evidence:** independent expected output, reference model, schema, or
   deterministic mutation classification.

A source-level unit test alone cannot close an installed-product or integration
claim. The first packaged QA pass is frozen before repairs; the final verdict is
based on a clean rerun after repairs.
