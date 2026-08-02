# Forecost production and adoption audit — 2026-08-02

Scope: current local branch `fix/meter-correctness-audit-remediation` at
`7ca26adf`, public repository `ArivunidhiA/forecost`, PR #2, the July research
and handoff corpus, relevant Codex/ChatGPT conversations from the last two
months, and the external repositories supplied by the maintainer.

This audit supersedes the implementation status in July's private `HANDOFF.md`.
That document recorded the meter as live-verified, but the July 17 audit later
proved that event duplication and incorrect pricing compounded into a material
overstatement. PR #2 fixes much of that root problem, but it is not safe to
merge yet.

## Executive verdict

Forecost has a credible open-source wedge: a local, independent receipt and
reconciliation layer for AI-agent usage. Its strongest assets are the
content-free Claude transcript adapter, multi-basis ledger, fail-open policy
law, honest shadow-mode estimator, and unusually broad cross-platform tests.

The audited branch is now a local release candidate. The implementation pass
closed the transaction, queue acknowledgement, recovery, guessed-price policy,
plugin supply-chain, destructive-command, privacy, and release-pipeline
blockers described below. The remaining merge gate is evidence from the remote
CI matrix; publishing 0.3.0 remains intentionally blocked while its changelog
entry is marked `Unreleased`.

The path to thousands of stars is not a larger feature list. It is:

1. make the meter boringly trustworthy;
2. make the first useful result take under a minute;
3. make every public surface tell the same honest story;
4. publish reproducible evidence and failure cases;
5. then expand ingestion to the agent harnesses people actually use.

## Evidence and verification

- GitHub: PR #1 is merged. PR #2 is open and mergeable. The previously failing
  Xenon paths now satisfy the gate; the updated branch still needs to be pushed
  and verified by the remote CI matrix.
- PR #2 automated review: 12 unresolved inline threads plus three additional
  out-of-diff correctness/security findings.
- Current public release: PyPI/GitHub `0.1.1`; local/plugin branch `0.3.0`.
- The public GitHub description/topics and the branch README/package/plugin
  metadata now lead with the local, content-free agent cost ledger. The
  published PyPI 0.1.1 page will remain old until a separately authorized 0.3.0
  release.
- Specialist reviews: security, performance/reliability, test/release, and
  code quality/architecture, merged here rather than copied as separate lists.
- Before edits, CI-equivalent Xenon failed at `scan_transcript_errors`,
  `recover_cmd`, and `reconcile_cmd`; those paths were decomposed and now pass.
- Final local evidence: 366 tests pass (plus one intentional skip) in the clean
  Python 3.12 environment; changed-line coverage is 92%; Ruff, formatting,
  Pyright, Xenon, Bandit, and
  `pip-audit` pass. Fresh wheel/sdist builds pass Twine and wheel-content checks,
  and a wheel installed outside the repository passes version/help/doctor/
  ledger smoke commands. Minimal-wheel median startup measured 29.5 ms for
  `--help` and 36.3 ms for `ledger status` on the audit host. Re-running the
  original 12-thread/3,600-event integrity probe produced 3,600 accepted events,
  zero exceptions, zero posting-less events, and zero duplicate posting keys.

## Implementation result

Completed in the audit remediation batches:

- atomic synchronous event/posting writes, serialized shared connections, and
  explicit async enqueue/drain durability outcomes;
- immutable loss-preserving dual-format recovery with exact-posting replay,
  ownership-marked allowlisted purge, strict migration timestamps, and
  conflict-safe one-per-estimate reconciliation;
- event-effective pricing with provenance and confirmed-only hard budget actions;
- stable identifier fallbacks, bounded transcript polling, current-streak guard
  semantics, and sink-enforced content-free metadata;
- private dynamic storage paths, full event-field validation, modern secret
  redaction, stable hashing of every open-ended persisted identifier, validated
  posting replay, refusal of unowned custom data roots, read-only-by-default MCP
  mutations, lazy CLI imports, and explicit
  (never lifecycle-triggered) plugin installation with fail-open launchers;
- pinned GitHub Actions, clean artifact/install gates, synchronized release
  versions, dependency automation, public positioning, architecture/contributor/
  security documentation, and targeted issue templates.

Still intentionally deferred: remote CI confirmation, PyPI/GitHub publication,
SBOM/provenance and repository protection settings, legacy MCP-to-ledger
migration, loopback HTTP authentication, aggregate/N+1 reconciliation work at
million-event scale, and new Codex/OpenCode/OpenClaw adapters.

## Ranked findings and implementation checklist

### P0 — must be fixed before PR #2 can merge

- [x] **P0-1 — Make synchronous ledger writes atomic.**
  `forecost/ledger/sink.py` can leave a visible `usage_events` row without
  postings if posting insertion or commit fails. A retry then sees a duplicate
  and the adapter can advance its cursor. Put workspace/session resolution,
  event insert, posting inserts, and commit in one transaction; roll back on
  every exception. Add fault-injection tests for posting and commit failure.
  The shared `check_same_thread=False` connection also needs serialization or
  replacement with connection-per-thread semantics: a 12-thread/3,600-event
  stress probe produced 1,672 exceptions and 448 posting-less events.

- [x] **P0-2 — Never acknowledge an async write that was dropped.**
  `LedgerWriteQueue.put()` logs queue overflow but returns normally;
  `DefaultLedgerSink.emit()` always returns `True`. Make enqueue acceptance
  explicit and propagate a transient failure so pull adapters retain their
  cursor. Preserve the product-level fail-open behavior at the hook boundary.

- [x] **P0-3 — Propagate drain/spill failure.**
  A drain barrier currently signals progress even when both database retries
  and recovery spill fail. Give barriers a success/error state, have `drain()`
  return the real durable result, and make `DefaultLedgerSink.flush()` surface
  failure to callers that require read-your-writes semantics.

- [x] **P0-4 — Make purge structurally safe.**
  `FORECOST_HOME` is environment-controlled and is passed to `shutil.rmtree`.
  `--yes` must never allow recursive deletion of `/`, the user's home, the
  current workspace, an ancestor, or a symlink escape. Delete only known
  Forecost-owned entries, refuse unsafe targets, and remove the directory only
  if empty. Add root/home/cwd/relative/symlink boundary tests.

- [x] **P0-5 — Do not hard-deny from guessed prices.**
  Unknown-model postings are marked `/unpriced-guess`, but canonical queries
  discard that confidence and the policy engine treats the guessed amount as
  fact. Propagate pricing confidence through policy measurements and fail open
  when no reliable priced value exists. Reporting may still show the clearly
  labeled estimate.

- [x] **P0-6 — Preserve recoverability on partial replay.**
  `forecost recover` archives the complete dead-letter file even when some
  records fail and always reports that it archived. Retain failed lines
  atomically, archive only after full success, and report the actual outcome.
  Schema-detect the legacy writer format or separate its dead-letter path: the
  current user recovery file contains 3,600 valid legacy-schema records that
  the new command cannot parse and would otherwise archive as failed.

- [x] **P0-7 — Remove mutable code installation from automatic hook startup.**
  The Claude plugin installs GitHub `main` during `SessionStart`. That is an
  automatic arbitrary-code supply-chain boundary, and it is POSIX-only despite
  the project's Windows story. Install an immutable released artifact during
  an explicit install/update step, or pin a reviewed commit and verified
  dependencies as an interim measure. Either support Windows with an executable
  launcher and first-run test or state the platform limitation honestly.

- [ ] **P0-8 — Restore a fully green PR gate.**
  Refactor the three Xenon failures, add tests for the new command branches,
  meet the 90% diff-coverage gate, and run smoke only after lint/security/test/
  coverage all pass. Do not merge based only on the 12 green OS/Python legs.
  The complete local equivalent now passes; this stays open until the pushed
  commit completes the remote matrix, coverage, and artifact-smoke jobs.

### P1 — production trust and release readiness

- [x] **P1-1 — Reject identifier-less Claude usage records.**
  Missing `requestId` and `uuid` currently collapse to `cc:uuid:`. Skip and log
  them or create a stable collision-resistant fallback from non-content
  metadata. Test multiple identifier-less records.

- [x] **P1-2 — Correct the guard's recent-window semantics.**
  The code calculates maximum streak and total errors over up to 4,000 records,
  and uses `any(last_five)` rather than whether the final result is an error.
  Calculate current streak and error count from the final tail window. Add
  recovery-after-errors regressions and reduce complexity below Xenon's gate.
  Poll only the hook's triggering transcript and reverse-read a bounded tail;
  the current Stop path scans a 1,492-file/1.46-GiB transcript tree and can load
  an entire 52-MiB file to inspect its tail.

- [x] **P1-3 — Stop fabricating migration timestamps.**
  Normalize valid legacy timestamps to aware UTC. Skip and count malformed
  rows instead of rewriting them to `now`, which contaminates rolling budgets
  and burn calculations.

- [x] **P1-4 — Fix basis-specific empty states and zero denominators.**
  `ledger by-workspace` must distinguish no workspaces from no spend in the
  requested basis. Reconciliation must flag `source_amount == 0` when the table
  amount is nonzero without dividing by zero. Restrict `pricing-audit` to USD
  until its output and table support other currencies.

- [x] **P1-5 — Apply the price effective on the event date.**
  Claude Sonnet 5 is officially `$2/$10` per MTok through 2026-08-31 and
  `$3/$15` afterward. The immediate table must use the current rate; the durable
  design must select an effective-dated price using the event timestamp so a
  future release does not reprice old usage incorrectly.

- [x] **P1-6 — Enforce the content-free invariant at the sink boundary.**
  Metadata restrictions are currently a convention. Validate keys, scalar
  types, lengths, and sizes; reject prompt/completion/tool-content fields and
  nested arbitrary data. Extend the privacy canary across sync/async sinks,
  recovery, LiteLLM, and legacy/manual APIs.
  Sink normalization now hashes open-ended event/session/run/model/provider/
  agent/metadata and posting identifiers; direct exact-posting replay centrally
  rejects invalid bases and non-finite, negative, boolean, or oversized amounts.
  The final independent canary probe found no raw canary anywhere in SQLite.

- [x] **P1-7 — Finish legacy-path privacy hardening.**
  `forecost/db.py` still bypasses `FORECOST_HOME`, canonical redaction, and
  explicit permissions. Route the legacy database, WAL/SHM, recovery, and logs
  through the same path/permission layer or clearly remove those surfaces from
  the supported product.

- [ ] **P1-11 — Bound hook and reconciliation latency.**
  Canonical session spend is currently a history-wide sort, measured at about
  32 ms on 39,759 events before process-start overhead, and reconciliation is
  N+1. Add scoped indexes/aggregates, set-based conflict-safe reconciliation,
  and duplicate Stop/SessionEnd protection. Establish p50/p95 gates at 40k,
  100k, and one million events.

- [x] **P1-12 — Make the current-product CLI cheap to start.**
  The CLI imports the superseded NumPy/statsmodels forecasting stack for every
  invocation; local cold start was roughly one second. Lazy-load commands and
  move legacy dependencies behind an extra, then benchmark the minimal wheel.

- [ ] **P1-8 — Harden the release trust boundary.**
  Require green CI before publish, assert tag/package/plugin/changelog version
  equality, run `twine check`, install the built wheel across supported Python
  versions, generate provenance/SBOM, pin GitHub Actions by commit SHA, and
  protect `main`, release tags, and the PyPI environment.
  Actions are SHA-pinned and the workflow now verifies source/tag/version,
  static/security/test gates, artifacts, and clean installs. SBOM/provenance
  generation and hosted repository/environment protection remain.

- [ ] **P1-9 — Align every public surface before 0.3.0.**
  Fix the README's outdated sample that still says
  `pricing_table + source_reported`; label all numbers synthetic; update the
  repository description/topics, PyPI description, CHANGELOG, plugin docs, and
  package metadata. The quickstart must use the real install path and produce a
  current ledger result in under a minute.
  Branch and GitHub repository surfaces are aligned; PyPI changes only when
  0.3.0 is deliberately published.

- [ ] **P1-10 — Test the artifact users install.**
  Execute README/plugin commands from clean wheel and sdist installs; test
  minimal install and every extra; test paths with spaces/non-ASCII; verify
  failure messaging when git/network/Python is unavailable.
  Clean minimal wheel/sdist build and smoke paths now pass locally and are in
  CI; the full extras/path/failure matrix remains follow-up coverage.

### P2 — next hardening and adoption wave

- [ ] Default the MCP server to read-only; require an explicit write flag,
  provenance, idempotency keys, and bounded values for mutation tools.
  Read-only default, explicit write opt-in, and bounded validation are done;
  idempotency/provenance and migration from the legacy database remain.
- [ ] Add a random token plus strict Host/Origin behavior to the loopback HTTP
  server and redact absolute paths by default.
- [ ] Make `init --smart` honor ignore rules, preview exact outbound files and
  bytes, scan secrets, delimit repository text as untrusted, and validate the
  model response with strict enums/ranges—or remove this legacy cloud path.
- [ ] Add dependency automation and reproducible clean environments; separate
  minimum-version compatibility from locked latest-resolution security checks.
  Dependabot and clean resolution audits are present; a locked latest/minimum
  split is still needed.
- [x] Improve error redaction for modern provider/GitHub/Bearer token formats.
- [ ] Reduce the sdist to intentional runtime/source artifacts.
- [ ] Add concurrency, hook-latency, transcript-scale, queue-durability, and
  reconciliation benchmarks; existing benchmarks cover the legacy forecaster.
- [ ] Rebuild MCP on the ledger rather than the legacy forecast database.
- [ ] Unify policy budgets and burn-rate budgets into one source of truth.
- [ ] Keep the estimator and guard shadow-only until independently labeled,
  held-out evaluations pass pre-committed gates.

## Implementation batches

### Batch 1 — integrity and destructive safety

P0-1 through P0-6 plus P1-1 through P1-5. These changes close silent data
loss, false denials, corrupted recovery, timestamp fabrication, and unsafe
deletion. They require unit, fault-injection, and CLI regression tests.

### Batch 2 — install, release, privacy, and public truth

P0-7/P0-8 and P1-6 through P1-10. This batch restores green CI, makes the
plugin install immutable/testable, tightens the privacy boundary, and aligns
GitHub/PyPI/README/release metadata.

### Batch 3 — 2026 agent reach

After 0.3.0 is trustworthy, prioritize ingestion in this order:

1. Claude Code stable fixtures and plugin distribution;
2. LiteLLM gateway reconciliation;
3. a read-only ledger MCP surface usable from many agents;
4. Codex/OpenCode/OpenClaw adapters after a shared session/run/span identity
   model exists;
5. effective-dated provider pricing and external bill adapters.

## What to borrow from the supplied repositories

| Repository | Decision | Forecost use |
|---|---|---|
| `karpathy/llm-council` | Borrow the method, not the app | Independent reviewers, anonymized ranking, chairman synthesis, and published evals are useful for pricing/adaptor audits. Do not add its web/OpenRouter stack to Forecost. |
| `ar9av/obsidian-wiki` | Borrow the memory discipline | Delta-based ingestion, explicit provenance (`extracted`/`inferred`), lint/dedup, and owned Markdown are strong patterns for project knowledge and audit history. Not a runtime dependency. |
| `JuliusBrussee/caveman` | Use as an experiment target | Its token-reduction claims are an excellent real workload for Forecost's independent before/after measurement. Do not make compressed agent speech a core feature. |
| `usestrix/strix` | Optional release/security exercise | Useful inspiration for executable security validation and CI evidence; too heavy and high-risk to make a default dependency. Run only in isolated, explicitly authorized targets. |
| `system_prompts_leaks` | Do not integrate | Leaked prompts are neither a stable API nor a safe product dependency. They may inform adversarial tests only after legal/security review. |
| `mattpocock/skills` | Borrow distribution quality | Small composable skills, editable cross-agent installs, clear ownership, and real-engineering workflows are excellent OSS presentation patterns. |
| `alirezarezvani/claude-skills` | Reference selectively | Useful taxonomy and cross-host packaging examples; importing hundreds of skills would dilute Forecost's wedge and expand the supply chain. |
| `ruvnet/ruflo` | Adapter target, not dependency | Ruflo represents the multi-agent usage Forecost should eventually meter. Its meta-harness is far too large to embed. |
| `AgriciDaniel/claude-obsidian` | Borrow release hygiene | Local-first ownership, privacy docs, checksums, release manifest, citation file, and explicit source-grounded workflow are strong repo-level patterns. |

## Adoption plan after the release gate

- Make the README answer three questions in ten seconds: what decision does
  this change, what data leaves my machine, and what command shows value now?
- Lead with the personal-data aha moment: ingest a user's own Claude history,
  show canonical spend, then show where prices were guessed or meters disagree.
- Publish a small synthetic/redacted fixture corpus and stable JSON snapshots so
  contributors can add harness adapters without private transcripts.
- Turn correctness incidents into trust assets: publish the 7.6x overstatement
  postmortem, the invariant tests it produced, and why the estimator remains
  hidden. Honesty is the differentiator.
- Add a contributor path for one new adapter in under an hour, with contracts,
  fixtures, privacy tests, and a pricing-confidence checklist.
- Do not add dashboards, payments, a cloud tier, or user-visible prediction
  ranges until real external adoption and held-out calibration justify them.

## Release gate

Do not call 0.3.0 production-ready until all are true:

- [ ] PR #2's unresolved correctness/security findings are fixed or explicitly
  disproven with tests.
- [ ] All CI jobs, including coverage and built-artifact smoke, are green.
- [x] No guessed price can trigger a hard deny.
- [x] Queue overflow, DB failure, torn input, and recovery failure cannot silently
  lose a billable event.
- [x] Purge cannot recursively delete a broad or user-controlled target.
- [ ] Plugin installation uses an immutable artifact and its supported platforms
  are executable-tested.
- [ ] README, GitHub metadata, package metadata, PyPI, plugin, and changelog agree.
- [x] A clean user can get a useful, honestly labeled result in under one minute.
- [x] The estimator and guard remain shadow-only.
