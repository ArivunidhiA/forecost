# Glossary and FAQ

## Glossary

**Adapter** — Code that maps one runtime, gateway, or offline format into
Forecost's bounded evidence contracts.

**Authority** — The economic role of a valuation source, such as provider
billed, gateway estimate, or list-rate equivalent.

**Canonical total** — One explicitly selected valuation per relevant fact and
line item for a particular view. Receipt v2 retains every active valuation
group and records which non-additive value was selected and why.

**Causal graph** — Runs, spans, parent relationships, links, branches, retries,
and waits describing how work led to other work.

**Charge/posting** — A source-specific valuation of a meter fact. “Charge” is
used in the receipt kernel and “posting” in the operational usage lane.

**Comparison arm** — A digest-bound baseline or candidate manifest containing
an exact configuration, source denominator, and matched case/attempt/run/
outcome/tariff roster.

**Comparison pass** — An observational matched cohort met both predeclared lower
confidence bounds. It does not mean causal savings, correctness, provider
billing, authentication, or release approval.

**Content-free (contract)** — Persistent current-product state is required to
exclude prompts, completions, tool payloads, source code, credentials, and raw
paths. Current Claude cursor/error paths use keyed identities, but the exported
legacy SDK can persist arbitrary raw name/path/metadata and custom out-of-root
state is not exhaustively discoverable. “Content-free end to end” is therefore
not a current claim.

**Evidence completeness** — Whether the sources/parts expected for a claim are
present under one named, versioned profile with a predeclared denominator. It is
independent of freshness and contradiction; receipt v2 makes no global
completeness claim.

**Finality** — How settled an observation is. This is independent of authority.

**Idempotency** — Replaying the same observation does not duplicate it; using
the same identity for different material is rejected.

**Ledger** — The canonical local `ledger.db` plus its operational and receipt
evidence models.

**List-rate equivalent** — A valuation calculated from a bundled public pricing
snapshot. It is not automatically what the provider billed.

**Meter fact** — A measured quantity such as tokens or calls, before money is
assigned.

**Outcome evidence** — A bounded user mark or command/test/build exit. It is not
proof of correctness.

**Projection** — Deterministic tables built from immutable journal observations
for querying and receipts.

**Pseudonymization** — Replacing raw identifiers or paths with normalized
labels, one-way hashes, or installation-keyed HMACs for grouping. Keyed Claude
cursor/error identities are harder to dictionary-recover after export than an
unkeyed hash, but this does not guarantee anonymity, unlinkability, or safety
from the same UID.

**Receipt** — Portable evidence for one run: topology, quantities, valuations,
authority, finality, outcomes, conflicts, blind spots, and integrity digest.

**Reconciliation** — An explicit comparison between independent evidence,
including coverage, matches, residuals, and unmatched items.

**Resource envelope** — Experimental single-host allocation/reservation/lease
logic. It is not provider-side or distributed enforcement.

**Run Lab** — Deterministic synthetic receipt scenarios that use isolated data.

**Shadow mode** — A calculation runs and is evaluated but is not presented as
user advice or an enforcement signal.

**Span key** — Internal deterministic identity derived from trace + span. It
prevents equal runtime span IDs in different traces from colliding.

**Timing state** — `complete`, `partial`, or `unknown` based on explicit timing
evidence. Observation timestamps are never substituted for span duration.

**Supersession** — New evidence replaces an earlier conclusion without silently
rewriting the historical observation.

## FAQ

### Is Forecost a cost tracker?

Partly, but that description is too small. It records measured quantities and
valuations, preserves their provenance, and explains the graph that produced
them. It is primarily an economic receipt and reconciliation system.

### Does it tell me my actual bill?

Only an authenticated provider source can establish provider-billed origin.
Current arbitrary JSON/CSV imports are always `user_imported_claim`; schema v11
append-supersedes proven historical local-import billing labels. No authenticated
provider profile has been implemented or live-validated. A local rate
calculation is a list-rate equivalent.

### Does it send prompts or code to a Forecost server?

The current receipt product has no hosted tier or network-backed ingestion.
Its typed evidence contracts reject prompt/tool/source content, and current
cursor/error paths use installation-keyed identities/fingerprints. The exported
legacy SDK is not fully isolated: it can persist arbitrary raw project
name/path/metadata in `costs.db`. Custom paths and same-UID access also remain
outside an end-to-end guarantee.

### Does the Claude plugin stop overspending?

It can make local `ask` or `deny` decisions when its evidence is healthy.
Interactive hooks fail open. An explicit protected CI policy or LiteLLM
constructor may fail closed on internal error, but neither mode can bound
provider-side, bypassed, or distributed work.

### Why are there two databases?

`ledger.db` is the v0.3 current product. `costs.db` is the retired v0.2 calendar
forecaster. They are intentionally separate; migration is explicit.

### Why are there two models inside `ledger.db`?

The July operational ledger and the August graph receipt kernel evolved in
parallel. The former serves usage/postings, policy, and calibration; the latter
serves journaled causal receipts. Some Claude hooks feed both, while other
adapters feed one. This is current architectural reality, not a hidden promise
of complete unification.

### Can I use it with OpenAI Agents or LangGraph today?

The repository proves offline mapping contracts against local fakes. It does
not claim installed, live runtime integration or complete observation.

### Can I compare any two runs and call the difference savings?

No. For valid existing runs, the run-ID mode always abstains because it lacks matched workload and
outcome evidence. Full comparison v1 requires digest-bound baseline/candidate
manifests, a strict predeclared policy, at least 30 exact pairs, final `delta`
meter facts with complete compatible USD list-rate valuation coverage,
predeclared deterministic test/build outcome evidence, and confidence bounds.
It verifies a WAL-consistent in-memory journal/projection rebuild before deciding
and abstains when reconciliation state is present but not journal-derived. Even
then the result is observational, and the manifests are self-attested rather
than authenticated.

### Why is forecast code still present?

Compatibility and calibration history. User-facing task forecasting is not a
current claim, and calendar CLI commands are isolated under `forecost legacy`.
Backward-compatible SDK exports remain and are a release blocker until removed
or constrained.

### Is 0.3.0 released?

The source declares 0.3.0, but `CHANGELOG.md` says Unreleased and the status
document retains the 2026-08-13 NO-GO. Current-ledger repairs do not satisfy the
external review, live provider, legacy privacy, public distribution, same-UID,
comparison field-validation, or demand gates. Treat the checkout as experimental.

### Where should I start coding?

Run the synthetic walkthrough, read the relevant ADR and tests, decide which
evidence lane the change belongs to, and make the smallest contract-preserving
change with an end-to-end synthetic proof.
