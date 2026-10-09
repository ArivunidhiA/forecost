# Current state and next work

This page describes the current documented repository state, not a promise
about a published package or an independent external audit. The authoritative
status retains the 2026-08-13 red-team NO-GO.

## Version and publication

- Source/package version: **0.3.0**.
- Product state: **experimental local**.
- Changelog state: **Unreleased**.
- Historical 2026-08-09 packaged QA verdict: **GO WITH KNOWN RISK** for founder
  review/controlled trials. The 2026-08-13 red team supersedes it with a
  **NO-GO release hold**. Current-ledger code repairs do not clear the remaining
  external-review, legacy, distribution, live-source, and field gates below.
- No tag, PyPI release, GitHub release, hosted deployment, or announcement is
  implied by this checkout.
- The public PyPI project still serves legacy 0.1.1 forecasting behavior; it is
  not this unreleased 0.3 source tree.

## Implemented and demonstrable

- Canonical local `ledger.db` at schema v11 with `synchronous=FULL`,
  transaction controls, and verified SQLite Backup API migration snapshots.
- Operational usage/posting ingestion and canonical selection that avoids
  summing competing valuations.
- Append-only causal journal and deterministic run/span/fact/charge projection;
  schema v10 uses a trace-scoped internal `span_key` and fails closed on an
  ambiguous legacy identity migration.
- Receipt/causal schema v2: explicit timing semantics, unknown/partial timing
  when intervals are insufficient, all valuation groups preserved, and a
  selected non-additive canonical value with reason.
- Named structural, economic-estimate, provider-billed, outcome, and CI evidence
  profiles with independent completeness/freshness/contradiction axes,
  predeclared denominators, unmet obligations, reason codes, and `as_of`.
- Stable text, JSON, and Markdown graph receipts using those v2 semantics.
- Strict read-only comparison v1: bare two-run diagnostics always abstain;
  digest-bound matched cohorts use a predeclared observational USD list-rate
  policy, at least 30 exact pairs, final `delta` meter facts with complete
  one-to-one valuation coverage, predeclared deterministic test/build outcome
  evidence, and deterministic confidence bounds. The engine evaluates one
  WAL-consistent in-memory backup after journal-chain and deterministic
  projection-rebuild/hash validation; invalid journal/projection/rebuild state is
  exit 4, more than 1,000,000 global journal rows is an abstention, and any
  non-journal-derived reconciliation batch forces abstention. Bootstrap seeding
  excludes caller-controlled identifiers.
- Deterministic Run Lab demo and chaos fixtures.
- Offline user-declared economic-claim and OTel-style evidence import. Arbitrary
  JSON/CSV is always `user_imported_claim`; schema v11 append-supersedes proven
  historical local imports previously labelled `billed`.
- Explicit reconciliation with source coverage and residuals.
- Journal/receipt integrity classification.
- Outcome capture and user marks.
- Current Claude cursor/error identities use installation-keyed HMACs, cursor
  file-identity/complete-prefix rewrite checkpoints, plus accidental single-file
  key/ID loss or mismatch detection for dependent canonical-home cursor state.
- Streaming privacy verification scans readable regular files and fails
  inconclusive on unreadable, symlinked, or non-regular skipped paths.
  Successful recovery durably publishes a finite summary before deleting a raw
  queue and retains the queue for retry if publication fails. Ownership-aware
  purge tooling covers the current known manifest under one Forecost home,
  including schema backups, crash temps, hook/outbox state, and identity keys;
  out-of-root paths remain outside a deletion claim.
- Interactive policy paths fail open; an explicit protected CI policy or
  LiteLLM constructor boundary can fail closed.
- Optional three-tool read-only MCP access for run listing, receipt retrieval,
  and always-abstaining two-run comparison diagnostics.
- Experimental Claude hooks/plugin, LiteLLM callback, and local resource
  envelopes. The source plugin uses an exact owner-controlled launcher with no
  `PATH` fallback and disables runtime bootstrap.
- Legacy CLI isolation behind `forecost legacy` and separate `costs.db`; the
  backward-compatible exported SDK is not yet isolated and remains a blocker.

## Experimental or deliberately narrow

| Area | Honest boundary |
| --- | --- |
| Claude Code | Best-effort local transcript/hook observation; partial graph; interactive fail-open; no supported production installer |
| LiteLLM | Gateway callback; usage/postings lane; no distributed guarantee |
| OTel | Offline file import, not a live collector |
| OpenAI Agents | Offline mapping against local fakes only |
| LangGraph | Offline mapping against local fakes only |
| MCP | Optional, three tools, stdio; comparison is diagnostic-only. Read-only means no Forecost row/schema mutation, but SQLite `mode=ro` may create/update WAL/SHM coordination sidecars; `immutable=1` is not used because it can miss committed WAL state. |
| Resource envelopes | Experimental, single host, no bound on outside/provider overrun |
| Estimator/guard | Shadow-only because validation is not yet strong enough |
| Pricing | Bundled snapshot; unknown/stale entries must remain visibly qualified |

## Known engineering and validation debt

- The two current-product evidence lanes are not fully unified.
- The exported legacy SDK and `costs.db` project/tracker paths can persist
  arbitrary raw project names, paths, and metadata. This prevents an end-to-end
  content-exclusion claim even though current cursor/error paths are keyed.
- Custom ledger/outbox locations, exports, and integration state outside
  `FORECOST_HOME` cannot be exhaustively discovered or removed by a root-scoped
  scan/purge.
- There is no authenticated provider profile, provider-billed live ingestion,
  or founder-approved live runtime/provider validation.
- The repaired worktree has internal automated/audit evidence, but no external
  independent privacy/security assessment. Internal subagent review must not be
  called independent.
- The public `main` branch and PyPI package remain the legacy product; no public
  installation path delivers this worktree.
- The narrow matched-run `compare` implementation exists, but its blinded
  ≥30% Forecost-only actionable-result, three recurring decision-class, and
  real-user retention gates have not been completed.
- Manual Claude ingest and LiteLLM do not automatically create complete causal
  receipt evidence; OTel import does not populate operational usage postings.
- Live runtime/provider completeness has not been proven by offline fakes.
- External Python/OS/optional-extra release validation and dependency advisory
  refresh remain publication gates.
- Packaged QA recorded significant surviving/timed-out mutation cases as
  quality debt.
- Very large graph output was measured below a million-span portable receipt;
  performance claims must stay within tested bounds.
- Same-user integrity is not signed or remotely attested.
- Real design-partner demand and retention gates are not yet satisfied.

## Product-validation gates

The planning docs call for evidence before broader investment:

- interview operators with real multi-source or graph-accounting pain;
- recruit design partners;
- observe actual receipt generation;
- find actionable discrepancies or decisions;
- measure whether users return in a second week;
- stop or reposition if those gates fail.

Resource controls should expand only if real incidents show that native
provider limits or simple counters do not solve the problem.

## Deliberately excluded from the current product

These are not accidental omissions:

- hosted dashboard/control plane;
- future task-cost forecasting as a user-facing promise;
- model routing or quality recommendations;
- generic trace/graph viewer;
- universal live framework support;
- signed certificates, remote attestation, or distributed hard enforcement;
- verified task correctness.

## Safest order for continued work

This is a documentation inference, not an approved roadmap:

1. keep contributor docs and capability claims aligned;
2. complete maintainer decisions about name, claims, release, and legacy timing;
3. refresh release matrices, advisories, and external review;
4. validate sanitized live runtime/provider samples;
5. run controlled design-partner trials and measure the published gates;
6. publish only when those gates and founder approvals are satisfied;
7. invest in additional adapters or enforcement only after field evidence.

Do not resurrect forecasting merely because old and shadow estimator code is
still present. The product contract and calibration verdict control that choice.

## Strategic research after the audited status

The 2026-08-13 [deep research and 90-day roadmap](../docs/research/2026-08-13-deep-research-roadmap.md)
and [50-repository landscape](../docs/research/2026-08-13-github-landscape.md)
recommend a measured next direction: one journal-first economic model, a focused
live MCP control surface, claim-profile evidence scoring, CI assertions, and
truthful assurance profiles plus mechanisms. Named receipt claim profiles and
the explicit CI failure boundary now exist at code level. The narrow comparison
prototype also exists, but its field proof does not. The live budgeting/loop
MCP, packaged assertion layer, broader journal unification, and adoption proof
remain proposals and test gates, not shipped public capabilities.

The later [startup-grade red team](../docs/research/2026-08-13-startup-grade-red-team-v2.md)
supersedes that strategy where it differs: preserve the kernel, fix the minimum
P0 receipt/privacy foundations, validate those repairs externally, and first
test one matched economic-evidence diff against native/adjacent tools. The
current worktree implements the code-level foundation but has not passed the
external or field gates. Only a ≥30% unique actionable-result gate earns the
broader Agent Run Lab/economic-debugger surface; otherwise evaluate a
protocol/merge/archive path. The
[master checklist](../docs/research/2026-08-13-master-product-launch-checklist.md)
contains the no-release gate and proposed execution order.
