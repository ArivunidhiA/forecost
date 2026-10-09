# Forecost product contract

> This file is normative intent, not proof that every implementation path
> satisfies it. The current worktree remediates the 2026-08-13 current-ledger
> identity, timing, valuation, evidence-profile, durability, cursor/log, purge,
> CI-mode, and launcher findings. The [status](status.md) records the remaining
> legacy-SDK, out-of-root state, live-source, external-review, publication,
> field-demand, and same-UID blockers. Status overrides this contract when
> describing implemented or releasable behavior.

**Contract version:** 1.0  
**Last reviewed:** 2026-08-13

## The customer and job

Forecost is for the engineer or platform team running autonomous coding or
workflow agents who cannot answer a simple operational question after a run:
what resources did this run consume, what did each independent source say it
was worth, what branches and retries caused it, and how complete is that
evidence?

The intended first product is a local, content-minimizing economic receipt. It is not an
agent orchestrator, a generic observability interface, a hosted control plane,
or a task-cost predictor.

## Product laws

1. **Evidence before advice.** Forecost records observations and disagreement;
   it does not present an estimate as a bill or a health score as safety.
2. **Content exclusion by intended construction.** Prompts, completions, tool
   payloads, source code, raw workspace paths, credentials, baggage, and
   tracestate do not enter persistent current-product evidence state. A
   compatibility surface that accepts arbitrary metadata cannot be part of this
   claim.
3. **Causal before aggregate.** Every total must be attributable to a stable
   run/span identity, source sequence, and immutable observation.
4. **Meter facts are not money.** Quantity observations and valuations remain
   distinct, and several valuations may legitimately describe one fact.
5. **Local controls are scoped claims.** A local hook can be observed or
   contained only within its stated process boundary; it cannot claim to stop
   provider-side work already admitted.
6. **Late evidence corrects by supersession.** Forecost never silently rewrites
   the historical observation that a prior receipt used.
7. **Portable output, not another dashboard.** The primary artifacts are stable
   text, JSON, and Markdown receipts.
8. **Matched evidence before comparison.** Two run totals are descriptive only.
   A comparison may qualify only under a predeclared, versioned policy that
   binds the exact case, configuration, source, tariff, receipt, and external
   outcome evidence; otherwise it abstains or rejects the evidence.

## Vocabulary and supported claims

| Term | Meaning | May Forecost claim it now? |
| --- | --- | --- |
| token usage | A local/runtime/gateway quantity observation | Yes, with source and finality |
| list-rate equivalent | A valuation from a bundled public rate snapshot | Yes |
| gateway estimate | A gateway-reported valuation | Yes, when imported |
| provider billed | A valuation from an authenticated provider source/profile for the relevant scope | Only after source authentication; an arbitrary local file is `user_imported_claim` |
| subscription quota | A quota observation, not currency spend | Yes, if the source provides it |
| reconciliation coverage | Expected versus present evidence for a named comparison profile | Yes for receipt-v2 named profiles within their declared denominator; completeness, freshness, and contradiction remain independent |
| wall timing and critical path | Service/wait interval unions plus elapsed envelope; critical path additionally requires typed scheduling dependencies | Complete explicit intervals support wall timing. Non-trivial critical path is currently withheld; only the trivial one-span case is populated. |
| hard enforcement | A resource cannot be overspent outside the stated boundary | Not yet; only local experimental boundaries are permitted |
| actual cost | Provider-billed authority for the relevant account/time window | Only with an authenticated provider source/profile and valid scope join |
| verified outcome | An explicitly recorded evidence item, such as a test exit | Yes, but never as proof a task was correct |
| matched economic/outcome comparison | An observed paired difference under a predeclared workload, source, tariff, and outcome contract | Experimental in comparison v1 for completely valued final `delta` meters in USD list-rate scope and deterministic test/build outcomes only; not a causal savings claim |

## Threat model

Forecost treats imported agent data, environment variables, repository-local
configuration, and hook input as untrusted.  The local ledger may reveal work
patterns even without content, so it is owner-only.  The product must resist
prompt/payload persistence, identifier/path disclosure, double-counted replay,
partial writes, stale reads at admission, and claims stronger than the evidence.
The same operating-system UID is not a cryptographic trust boundary: local HMAC
identities, journal chains, and receipt digests do not provide remote
attestation or protection from same-UID replacement.

Comparison manifests are caller-supplied attestations, not authenticated third-
party statements. Their digest binding detects inconsistency within the local
artifact set; it does not prove assignment integrity, evaluator independence,
provider origin, or freedom from same-UID replacement.

The current comparison strengthens local consistency by copying one
WAL-consistent state into memory, verifying the journal chain, and
deterministically rebuilding/hash-checking journal-derived projections before a
decision. This does not authenticate the database. Reconciliation batches are
not journal-derived in v1, so their presence must cause abstention rather than
inherit the validated label.

## Evidence gates

An adapter or command may move from experimental to supported only when it has:

- a field-allowlisted contract and synthetic conformance fixture;
- deterministic replay and idempotency coverage;
- documented identity, authority, finality, and failure boundaries;
- a receipt that makes missing or contradictory evidence visible; and
- an end-to-end test from input fixture through public output.

A comparison additionally requires a frozen exact roster, distinct attempts and
runs, predeclared deterministic test/build outcome evidence, compatible
economic scope, final `delta` meters with complete one-to-one valuation
coverage, a minimum cohort declared before evaluation, and explicit uncertainty.
The current implementation bounds journal validation at 1,000,000 global rows
and seeds its deterministic bootstrap from sorted quantitative observations—not
caller-chosen labels. The current normative v1 details and stable exit meanings are in
[`comparison.md`](comparison.md).
