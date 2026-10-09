# Forecost completion checklist

> **Superseded as a release decision on 2026-08-13.** Checked boxes below record
> what the 2026-08-09 implementation effort believed it had completed. A later
> source/security red team found P0 raw-path/log, trace identity, timing,
> competing-valuation, evidence-denominator, authority, purge, durability,
> fail-closed, and installer defects. The current worktree has internal repairs
> for those current-kernel paths, while external review, legacy-state,
> authenticated-source, live-runtime, and publication gates remain open. Use
> [`status.md`](status.md) and the
> [master product/launch checklist](research/2026-08-13-master-product-launch-checklist.md).
> This file does not authorize release or substitute for current receipt-v2 and
> privacy evidence.

**Execution branch:** `codex/forecost-product-core`  
**Scope frozen:** 2026-08-09  
**Authority:** this file tracks the work required before Forecost is ready for
founder review. The larger design inventory remains in
[`master-checklist.md`](master-checklist.md).

## How to read this checklist

- `[x]` means implemented and covered by repository evidence.
- `[ ]` means autonomous work Codex must finish on this branch.
- `[~]` means staged for the founder, real users, or an external system; it is
  intentionally outside autonomous implementation.
- `[—]` means deliberately excluded from this build.

“Complete” in this file means a clean installed artifact passes its product,
privacy, integrity, failure, performance, and user-journey gates. It does not
mean published. No network-backed ingestion, account access, release, merge,
announcement, or real-user validation is authorized by this checklist.

## Product boundary already established

- [x] Freeze the product as a local, content-free economic receipt for agent
  runs—not a task-cost predictor, hosted control plane, or generic graph UI.
- [x] Record causal identity, lifecycle, operation kinds, retries, branches,
  checkpoints, meter facts, independent valuations, authority, finality, and
  outcome evidence in a versioned canonical ledger.
- [x] Add deterministic offline Run Lab demos and graph-chaos fixtures.
- [x] Add stable text, JSON, and Markdown receipts, run list/show, receipt diff,
  and explicit user outcome marks.
- [x] Add offline JSON/CSV provider, gateway, and OTel-style import with
  aggregate reconciliation that preserves unmatched evidence.
- [x] Add experimental single-host reservations, leases, fencing, settlement,
  release, expiry, recovery, and O(1) counters.
- [x] Add privacy verification, receipt snapshot digests, a field-level data
  inventory, pseudonymous workspace paths, and non-mutating Claude diagnostics.
- [x] Quarantine forecast-era CLI commands under `forecost legacy` while
  retaining temporary compatibility aliases.
- [x] Expose canonical read-only run and receipt queries through MCP.
- [x] Establish one Python runtime version authority and release-metadata checks.

## Autonomous implementation — product truth and compatibility

- [x] Make README, package metadata, plugin docs, command help, doctor output,
  examples, and status agree exactly with the product contract.
- [x] Remove claims of hard budget enforcement, verified safety, “actual” cost,
  or live completeness when the available authority does not support them.
- [x] Remove `forecost-mcp` from the base wheel or make its dependency and
  failure mode self-contained; no installed entry point may be broken.
- [x] Migrate every retained MCP read to canonical ledger queries; isolate or
  remove legacy MCP write/forecast tools from the supported surface.
- [x] Remove the unauthenticated legacy HTTP server from supported commands or
  constrain it to a clearly experimental, safe local surface.
- [x] Retire `init --smart` from the supported surface so the current product has
  no content-upload exception.
- [x] Make current and legacy databases impossible to confuse; every command
  must declare and test which store it reads or writes.
- [x] Generate or release-check `docs/status.md` and the capability matrix so
  shipped claims cannot drift from tests and public artifacts.
- [x] Finish compatibility rules for unknown receipt fields, old ledger rows,
  forward-only migrations, backups, dry runs, decimal/micros conversion, and
  preservation of legacy evidence without elevating its authority.

## Autonomous implementation — receipt and reconciliation quality

- [x] Complete the synthetic corpus for fan-out/fan-in, retries, cancellation,
  failure, handoff, checkpoint/resume, durable replay, late evidence, ambiguous
  identity, and partial observation.
- [x] Add deterministic crash injection before/after journal append, ledger
  commit, reservation, settlement, and reconciliation finalization.
- [x] Use the same conformance corpus across unit, property, integration,
  performance, documentation, and installed-artifact tests.
- [x] Correct receipt duration, wait time, critical path, source coverage, and
  evidence-state behavior for incomplete and contradictory DAGs.
- [x] Auto-capture content-free local test/build and Git commit/revert facts as
  explicit outcome evidence, with no inference that a task is correct.
- [x] Make text, JSON, and Markdown receipts exactly equivalent and add stable
  no-color, narrow-terminal, deterministic-time, screen-reader-friendly output.
- [x] Add provisional/final/superseded reconciliation; late evidence must reopen
  a batch rather than silently rewriting history.
- [x] Add event-level and aggregate set reconciliation with deterministic
  unmatched/ambiguous results and no competing-valuation double count.
- [x] Add tariff provenance and a reproducible historical valuation audit.
- [x] Stream large imports and reconciliation, and enforce an explicit measured
  full-receipt boundary with documented row, transaction, and output bounds.

## Autonomous implementation — resource ownership

- [x] Complete typed resource scopes for money-by-authority, tokens, calls,
  tool invocations, elapsed time, retries, branches, and concurrency slots.
- [x] Implement atomic parent/child transfer and split, stable retry identity,
  finalization reserve, per-branch caps, retry budgets, and concurrency limits.
- [x] Prove conservation across reserve, transfer, settle, release, expiry,
  recovery, duplicate delivery, late settlement, restart, and cancellation.
- [x] Separate shadow, warn, ask, deny, and CI fail-closed behavior; print the
  threat boundary and maximum possible overrun beside any containment claim.
- [x] Add structural loop facts (repeated operation signature, error streak,
  no-progress streak, branch growth) without inspecting content.
- [x] Add process-safe admission and multi-process tests for 100+ concurrent
  children; benchmark against a simple counter baseline.

## Autonomous implementation — adapter protocol and Claude lifecycle

- [x] Define a versioned adapter capability protocol for identity, delivery,
  graph coverage, usage, valuation authority, finality, replay, and enforcement.
- [x] Add an adapter conformance harness and CLI report with identity, duplicate,
  late-event, privacy, crash, finality, and receipt checks.
- [x] Upgrade Claude JSONL ingestion to preserve available parent/subagent,
  branch, tool-use/result, lifecycle, and interruption identity without content.
- [x] Replace LiteLLM callback-path analytical writes with a bounded durable
  queue, idempotency, poison-record handling, and queue age/depth diagnostics.
- [x] Finish a file/stdin OTel GenAI span-and-metric adapter.
- [x] Add offline-only OpenAI Agents SDK and LangGraph mappings against local
  fakes and golden fixtures; document unsupported/ambiguous identity explicitly.
- [x] Add compatibility fixtures for supported Claude, LiteLLM, OTel, OpenAI,
  and LangGraph shapes without importing their optional SDKs in the base wheel.
- [x] Make the installed CLI the sole Claude runtime authority; plugin scripts
  must be thin launchers and version-compatible manifests.
- [x] Finish `setup claude --dry-run`, isolated apply/check/repair/uninstall, and
  `self-test claude` against the exact packaged launcher and hook configuration.
- [x] Cover current Claude lifecycle events including plan exit, tool completion,
  subagent start/stop, task completion, stop, and session end.
- [x] Add a tiny synchronous pending marker/heartbeat on SessionEnd followed by
  idempotent reconciliation; stale or missing observation must be visible.
- [x] Add content-free statusline and post-turn receipt summary with bounded
  latency and clear `NOT OBSERVED` / `OBSERVED` / `CONTAINED` language.
- [—] Match additional Claude tool/MCP surfaces only after field demand and
  proof that the hot gate remains O(1) at its published latency target.

## Autonomous implementation — privacy, integrity, and operations

- [x] Route persistent identifiers and stored external fields through typed
  normalization, irreversible pseudonymization, or an explicit bounded
  enum/code.
- [x] Add monotonic journal sequence and chained digests that distinguish intact,
  truncated, rewritten, deleted, reordered, duplicated, and forked histories.
- [x] Expand `forecost verify` to return deterministic machine-readable results
  for every mutation class and receipt snapshot.
- [x] Harden all files against symlinks, unsafe ownership, broad permissions,
  traversal, non-atomic replacement, and untrusted repository configuration.
- [x] Publish and test the same-user threat boundary; local hooks cannot defend
  against an owner deliberately changing their own code or ledger.
- [x] Add structured local operational events and doctor health rules for ingest,
  watermarks, queue lag, duplicates, conflicts, reconciliation, recovery, and
  zero-usage-versus-stale-source distinction.
- [x] Add 40k, 100k, 250k, and 1M-event performance scenarios with explicit
  latency and memory budgets for ingest, admission, receipt, and reconciliation.
- [x] Enforce bounded transaction sizes, batch writes, indexed access paths, and
  no analytical SQLite work on supported asynchronous callback paths.

## Autonomous implementation — exhaustive QA and release-ready artifacts

- [x] Add property/state-machine coverage for journal writes, reconciliation,
  resource conservation, and crash recovery.
- [x] Add multi-process concurrency plus SQLite busy/full/corrupt, partial-file,
  permission, symlink, disk-full simulation, and interrupted-upgrade tests.
- [x] Add golden CLI tests for empty, first use, degraded, partial, conflicting,
  migrated, and large histories.
- [x] Block network access in unit, conformance, simulator, adapter, and installed
  artifact tests; no secret or API key may be required.
- [x] Build from a clean committed state and install-test the base wheel in a new
  temporary environment using the available local Python runtime.
- [~] Install-test every optional extra across the supported Python/OS matrix in
  release CI; doing so requires package indexes and external runners.
- [x] Run lint, format check, Pyright, MyPy, complexity, dead-code, Bandit,
  secret, wheel-content, metadata, and release validation locally.
- [~] Refresh the dependency advisory query in release CI; this offline run
  intentionally blocked the vulnerability service.
- [x] Run and preserve a selective mutation baseline for current policy,
  integrity, and watermark code; do not disguise surviving mutations.
- [—] Promote the baseline into a must-kill mutation-score gate only after
  equivalent mutations and whole-module timeouts are classified.
- [x] Produce a pinned Python 3.12 base constraint snapshot, SBOM, checksums,
  and local provenance metadata without signing or publishing them.
- [x] Write and test a five-minute synthetic journey and fake graph-runtime
  journey using the exact installed artifact.
- [~] Validate a real-history import only from founder-approved sanitized data.
- [x] Generate deterministic demo output, example receipts, architecture tour,
  adapter guide, migration guide, comparison matrix, release notes, contribution
  guide, security policy, and focused issue templates.
- [x] Execute the Claude `/qa` protocol: freeze initial packaged-product findings,
  test clean and upgrade states through the real CLI, repair autonomous findings,
  rerun from clean state, and issue exactly one final release verdict.
- [x] Reconcile this checklist against tests and artifacts; no box may be closed
  from code inspection alone.

## Deliberately excluded from this implementation

These were explicitly excluded by the founder from the implementation batch.
They remain research ideas, not hidden release requirements.

- [—] Economic Trace Fingerprint.
- [—] Counterfactual tariff revaluation as a user-facing feature.
- [—] Resource Proof Receipt, Merkle evidence roots, cap-soundness certificate,
  and receipt-carried linearizability witness.
- [—] Meter Disagreement Explainer as a predictive/classification product.
- [—] Budget Shadow Replay and strategy cost-profile features.
- [—] Local-key signed checkpoints or portable signed receipts.
- [—] AutoGen and Temporal integrations before demonstrated user demand.
- [—] Hosted control plane, dashboard, task-cost forecasting, model routing,
  generic graph viewer, or dependencies on leaked prompts.

## Founder/manual work — staged, not blocking autonomous completion

- [~] Confirm target segment, artifact, product name, legacy removal policy,
  identifier policy, outcome vocabulary, enforcement language, license stance,
  and final public claims.
- [~] Decide whether/when to merge, tag, publish to PyPI/GitHub/marketplace,
  protect branches/releases, and operate community or sponsorship channels.
- [~] Review migration backups and run any irreversible migration against real
  user data only after a restore drill.
- [~] Supply or approve sanitized real provider exports and real runtime samples;
  no autonomous task may access accounts, transcripts, or credentials.
- [~] Conduct maintainer/operator interviews, recruit design partners, and apply
  the product-demand and resource-control continuation gates.
- [~] Validate real provider billing nuances and runtime identity/finality with
  maintainers; obtain an external security/privacy review.
- [~] Run final publication checks from unrelated machines/accounts, announce the
  release, collect field feedback, and decide subsequent roadmap investment.

## Completion gate

Autonomous work is complete only when every unchecked item above is either
implemented with evidence or moved here with a concrete external dependency,
the `/qa` report contains one defensible verdict, the working tree is clean,
and publication is the only consequential action left.
