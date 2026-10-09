# Forecost status — 2026-08-13

<!-- package-version: 0.3.0 -->
<!-- capability-schema-version: 1 -->
<!-- product-contract-version: 1.0 -->

## Current product state

Forecost 0.3.0 is an **unreleased experimental local economic-receipt product**.
Its canonical store is `~/.forecost/ledger.db`; its intended contracts retain
content-minimized causal, meter, valuation, authority, finality, and outcome
evidence. Deterministic Run Lab fixtures and offline imports can exercise the
product without accounts, credentials, transcript content, or network access.

An in-place upgrade is **not** a historical-data sanitizer. The repaired write
paths constrain newly written state, but an existing Forecost home can still
contain bytes written by an older version:

- raw Claude transcript paths and prompt identifiers in `ingest_state` remain
  until the corresponding usage and causal cursor migrations run;
- a pre-hardening free-text `error.log` remains intact until the next diagnostic
  write replaces it (or the operator explicitly removes it);
- preexisting hook, outbox, and recovery files are not rewritten merely because
  the package or ledger schema was upgraded; and
- a `ledger migrate-schema` backup is intentionally an exact pre-migration
  SQLite snapshot. A pre-v11 backup may therefore retain raw cursor keys and
  values even after the live ledger is remediated.

Those retained artifacts must be inventoried and treated as sensitive. Forecost
does not silently delete an exact rollback image or an undrained operational
queue. A schema version, a successful install, or one post-upgrade write is not
evidence that the complete upgraded home satisfies the repaired at-rest
contract. See [the data inventory](data-inventory.md#in-place-upgrade-truth).

## 2026-08-13 red-team hold

A post-QA source/security audit found release-blocking defects. The current
worktree implements the following code-level remediations:

- schema v10 derives a deterministic `span_key` from trace + span and rebuilds
  projections transactionally, failing closed on ambiguous legacy identity;
- receipt/causal schema v2 accepts only explicit interval or explicitly
  reported-duration semantics, never observation latency as duration; complete
  explicit intervals support service/wait unions and an elapsed envelope, while
  non-trivial critical path is withheld until scheduling dependencies are typed
  (only the trivial one-span case is populated);
- receipt v2 preserves every active valuation group and records the selected,
  non-additive canonical value and reason;
- named claim profiles declare denominators and report completeness, freshness,
  contradiction, unmet obligations, reason codes, and `as_of` independently;
- arbitrary JSON/CSV imports are `user_imported_claim`; schema v11
  append-supersedes proven historical local imports previously labelled
  `billed`, preserving the journal and provenance;
- newly written or lazily migrated Claude cursors and new error details use
  installation-keyed HMAC identities or finite codes/fingerprints; cursor
  complete-prefix checkpoints detect same-path rewriting; accidental loss,
  corruption, or mismatch of one key/ID file fails when dependent keyed state
  is visible in the canonical home, while coordinated same-UID replacement of
  both remains undetectable;
- privacy verification streams readable regular files in the selected home
  without a size skip and fails inconclusive on unreadable, symlinked, or
  non-regular skipped paths; successful recovery durably publishes a finite
  replay summary before deleting the raw queue, retaining the queue for
  idempotent retry if publication fails; the purge manifest includes current DB
  sidecars, recovery/hook/outbox state, identity keys, migration backups, and
  crash temps;
- canonical SQLite connections use `synchronous=FULL`; migrations create and
  verify a standalone SQLite Backup API snapshot, including committed WAL pages;
- interactive policy failures remain fail-open, while an explicit protected CI
  mode may choose fail-closed; and
- the Claude launcher resolves only the exact owner-controlled plugin-data
  executable with no `PATH` fallback, while runtime bootstrap is disabled; and
- a narrow `forecost compare` prototype separates always-abstaining two-run
  diagnostics from digest-bound matched cohorts. Its v1 policy is observational
  USD list-rate equivalent only, requires at least 30 exact pairs, predeclared
  deterministic test/build outcome evidence, final `delta` meters with complete
  one-to-one valuation coverage, compatible tariffs and sources, and confidence
  bounds. It evaluates a WAL-consistent in-memory backup after journal-chain and
  deterministic projection-rebuild/hash validation. Journal/projection/rebuild
  failure is invalid, more than 1,000,000 global journal rows is a bounded-work
  abstention, and any non-journal-derived reconciliation batch forces
  `RECONCILIATION_EVIDENCE_UNVERIFIED` abstention. Its deterministic bootstrap
  seed excludes caller-controlled labels.

These are implementation changes and internal test/audit evidence, **not an
independent external review or publication approval**. The 2026-08-13 NO-GO
remains because:

- the exported legacy SDK and `costs.db` paths can still retain arbitrary raw
  project name, path, and metadata;
- user-configured ledger/outbox or other state paths outside `FORECOST_HOME`
  cannot be exhaustively discovered or purged;
- no authenticated provider profile or live provider/runtime validation exists;
- no independent external privacy/security audit has reviewed the repaired
  implementation;
- no supported, operator-approved end-to-end upgrade sanitizer currently
  remediates every pre-hardening cursor, log, hook, outbox, recovery, and exact
  rollback-backup artifact;
- public `main` and PyPI still expose the legacy product;
- the narrow comparison prototype has not passed its blinded 30-run
  differentiation, real-user demand, or retention gates; and
- a process with the same operating-system UID remains outside the local
  integrity boundary.

Consequently state created entirely by the repaired checkout is
**content-minimizing within its documented current-ledger and owned-home
paths**. An in-place upgraded home is not proven to satisfy that boundary until
its historical artifacts have been separately inventoried and remediated. The
product is not proven content-free end to end.

Provider-billed, purge-complete, durable-under-all-failures, and tamper-proof
claims are not made. Timing and evidence claims are valid only for their named
semantics/profile. See the
[startup-grade red team](research/2026-08-13-startup-grade-red-team-v2.md).

The separate `~/.forecost/costs.db` file belongs to the retired v0.2 calendar
forecaster. Legacy CLI commands are routed through `forecost legacy …`, and
`forecost migrate` is an explicit copy path. However, backward-compatible SDK
symbols are still exported and can reach legacy storage directly; this is why
the legacy surface is a remaining privacy/release blocker. Legacy commands have
no hidden root aliases, `init --smart` has been removed, and the unauthenticated
loopback HTTP server has no CLI registration and is not a current API.

## Supported claims

- Text, JSON, Markdown, CLI, and optional MCP receipts are experimental views of
  canonical ledger evidence, not provider invoices. Receipt v2 retains all
  active valuation groups and identifies the canonical non-additive selection.
- Receipt v2 reports named structural, economic-estimate, provider-billed,
  outcome, and CI profiles. A profile's completeness, freshness, and
  contradiction are independent; there is no global completeness claim.
- Imported provider or gateway amounts from arbitrary local files are
  `user_imported_claim`, regardless of a filename or user-selected source; the
  current CLI has no authenticated provider profile that can emit `billed`;
  list-rate equivalents remain independent valuations.
- Claude Code and LiteLLM integration is experimental observation. Interactive
  paths are fail-open; only an explicit protected CI configuration may fail
  closed. Neither mode claims provider-side or distributed containment.
- OpenAI Agents and LangGraph support is currently an offline mapping contract
  proven against local fakes; it does not imply an installed SDK or live runtime.
- Resource envelopes are experimental, single-host controls. Their published
  boundary does not imply a bounded provider-side overrun; maximum overrun
  outside the local transaction boundary is not bounded.
- Explicit test/build exits and user marks are outcome evidence, never proof that
  a task is correct.
- A bare comparison of two valid existing runs may report an authority-specific observed delta but
  always abstains. Only the strict manifest-and-policy mode can return a
  qualified observational pass/fail, and v1 is limited to complete valuations of
  final `delta` meter facts in USD list-rate scope plus bound, predeclared
  deterministic test/build outcome evidence. Comparison reads one validated
  in-memory snapshot; non-journal reconciliation state cannot qualify. It is not
  a causal savings, provider invoice, or authenticated-manifest claim.

## Shipped interface boundary

- The root CLI lists current receipt-product commands and prints each command's
  store boundary. Retired commands require the `legacy` namespace.
- The optional MCP module is read-only and exposes
  `forecost_list_runs`, `forecost_get_receipt`, and the always-abstaining
  diagnostic `forecost_compare_runs` against `ledger.db`. The base wheel
  intentionally has no `forecost-mcp` console entry point; after installing
  `forecost[mcp]`, use `python -m forecost.mcp_launcher`. This is not the
  proposed four-tool live budget/recording MCP. “Read-only” means no Forecost
  row/schema creation, migration, insertion, update, or deletion; SQLite
  `mode=ro` may still create or update WAL/SHM coordination sidecars. The server
  does not use `immutable=1`, which could omit committed WAL state.
- `docs/capabilities.json` is the machine-readable authority for adapter,
  interface, store, and claim boundaries. The release validator checks its
  version and required contract fields against this status file and package
  metadata.

## Not claimed

Live provider billing APIs, provider-billed authority without an authenticated
provider source/profile, causal savings attribution, authenticated comparison
manifests, complete graph identity across every runtime, verified task
correctness, distributed enforcement, task-cost forecasting, and a hosted
control plane are not part of this release. Neither is exhaustive deletion of
custom paths outside `FORECOST_HOME`, legacy-SDK content exclusion, or integrity
against code running as the same UID.

## Publication state

The 0.3.0 changelog remains `Unreleased`. No PyPI release, GitHub release, tag,
merge, announcement, or real-data migration is implied by this branch. Those
remain founder-controlled actions after P0 remediation, a fresh independent
external privacy/security review, claim review, and the applicable field
gates—not merely the historical packaged-product QA pass or internal subagent
audit.

## Packaged-product QA

The corrected base wheel was built offline from the clean product-core branch,
passed Twine and wheel-content inspection, and completed installed CLI journeys
for first use, receipt equivalence, empty/degraded input, schema upgrade with
backup, Claude setup/self-test/uninstall, privacy verification, and journal
tamper classification. Checksums, an SPDX SBOM, and unsigned local provenance
were generated. The detailed evidence and residual risks are in
[`qa/final-report.md`](qa/final-report.md).

That historical upgrade journey verified the SQLite schema and rollback image;
it did not prove that pre-hardening cursor rows, diagnostics, hook/outbox/
recovery files, or the exact backup had been sanitized. It must not be cited as
an owned-state privacy migration pass.

Publication is held for the remaining blockers above, current
dependency-advisory refresh, the external Python/OS/optional-extra matrix,
founder-approved live-runtime samples, independent external privacy/security
review, public-claim review, and the matched-run field-demand gate. The current
selective mutation baseline is also recorded as quality debt rather than
represented as a passing score.
