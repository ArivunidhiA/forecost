# Testing and contributing

Forecost is an evidence system. Tests must cover not only the happy path, but
also the conditions that make accounting systems fail: replay, duplication,
late evidence, partial input, stale state, conflicting authority, and recovery.

## Before editing

1. Read the committed `AGENTS.md`; use the optional repository knowledge graph
   first only when its local tools are actually available.
2. Read the relevant product law and ADR.
3. Decide whether the change belongs to the operational usage lane, receipt
   lane, both lanes, or legacy compatibility.
4. Inspect the command's stated store boundary.
5. Check the worktree and preserve unrelated user changes.

## Test layers

| Layer | What it proves | Examples |
| --- | --- | --- |
| Unit/contracts | Validation, normalization, calculation | pricing, scope, policy, contracts |
| Adapter conformance | identity, replay, cursors, failure, privacy | Claude, LiteLLM, causal protocol tests |
| Ledger kernel | transactions, schema, journal, projections | ledger schema, writer, integrity tests |
| Product output | stable receipt/reconciliation/comparison behavior | receipt, runs, reconcile, compare, MCP tests |
| Security/privacy | rejected content, safe paths, safe deletion | privacy canary, permissions, purge tests |
| Lifecycle/recovery | hooks, queues, crashes, replay | hook, spool, recover, outbox tests |
| Property tests | invariants across generated cases | property-based and edge-case suites |
| Performance | bounded hot paths and large graphs | benchmark and release-evidence tests |
| Packaging | wheel contents and installed behavior | metadata, plugin manifest, MCP launcher tests |

## Minimum local checks

```bash
pytest tests/ -v --tb=short
ruff check forecost/ tests/
ruff format --check forecost/ tests/
pyright
mypy forecost/
```

Before a substantial PR, also run complexity, security, dependency, and
coverage checks listed in [Developer setup](10-DEVELOPER-SETUP.md).

## Adding an adapter

A trustworthy adapter needs all of the following:

- one provider response maps to one stable identity across replay;
- retries remain separate attempts rather than duplicates;
- the cursor advances only after accepted durable output;
- same-path input replacement cannot silently skip new bytes;
- torn or malformed input is retried, quarantined, or reported explicitly;
- persisted metadata uses bounded operational scalars only;
- source-reported and pricing-table values keep separate authority;
- unknown pricing is visibly guessed and cannot support a hard deny;
- optional SDK imports do not break the base CLI;
- tests cover duplicate replay, resume, partial input, sink failure, late
  evidence, finality, and the privacy canary;
- an end-to-end synthetic fixture reaches a public receipt or other declared
  interface.

Update `docs/capabilities.json` only to the capability actually proven. A local
fake proves a mapping contract, not live runtime support.

## Changing the ledger

The canonical schema uses a forward-only version ladder. A schema change needs:

- deterministic migration and fresh-database behavior;
- upgrade tests from relevant previous versions;
- backup/restore instructions when user data is affected;
- preservation of identity, authority, finality, and integer-micros values;
- transaction and concurrent-writer review;
- receipt and machine-readable output compatibility review.

Current landmarks are canonical schema v11 and receipt/causal schema v2.
Projection joins must use trace-scoped `span_key`, observation time must never
become duration, all valuation alternatives must remain portable, and evidence
claims must stay attached to a named versioned profile. Migration backups must
continue to use a verified SQLite Backup API snapshot rather than copying only
the main DB file while WAL pages may be committed.

Never silently elevate legacy observations into provider-billed or final graph
evidence.

## Changing comparison

Read [`docs/comparison.md`](../docs/comparison.md) before changing the engine or
CLI. Preserve these non-negotiable tests: two-run diagnostics always abstain;
full mode uses exact digest-bound rosters and distinct attempts/runs; unsupported
authority/currency/outcomes are rejected; missing, ambiguous, contradictory, or
tariff-mismatched evidence cannot qualify; the minimum remains at least 30
pairs; confidence output is deterministic; and decision/exit mappings remain
stable. A test fixture can prove implementation behavior, not real-world
assignment quality, causal savings, or demand.

## Changing claims or documentation

Words such as “actual,” “verified,” “complete,” “contained,” and “supported”
are technical claims in this project. Tie them to authority, completeness,
scope, and evidence. Update the contract/capability/status documents together
when a release boundary changes.

## Pull request checklist

- The change has one clear product purpose.
- Storage lane and store boundary are explicit.
- Privacy impact is described.
- Duplicate, late, partial, and failure behavior are tested as applicable.
- Text/JSON/Markdown outputs remain semantically consistent.
- Current and legacy surfaces remain isolated.
- Exported legacy SDK persistence is called out explicitly until it is removed
  or constrained; do not extend its arbitrary metadata surface.
- No private transcript or local database enters a fixture.
- Documentation distinguishes implementation, experiment, inference, and
  unsupported claim.
