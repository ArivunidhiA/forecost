# Forecost product contract

**Contract version:** 1.0  
**Last reviewed:** 2026-08-02

## The customer and job

Forecost is for the engineer or platform team running autonomous coding or
workflow agents who cannot answer a simple operational question after a run:
what resources did this run consume, what did each independent source say it
was worth, what branches and retries caused it, and how complete is that
evidence?

The first product is a local, content-free economic receipt.  It is not an
agent orchestrator, a generic observability interface, a hosted control plane,
or a task-cost predictor.

## Product laws

1. **Evidence before advice.** Forecost records observations and disagreement;
   it does not present an estimate as a bill or a health score as safety.
2. **Content-free by construction.** Prompts, completions, tool payloads,
   source code, raw workspace paths, credentials, baggage, and tracestate do
   not enter persistent Forecost state.
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

## Vocabulary and supported claims

| Term | Meaning | May Forecost claim it now? |
| --- | --- | --- |
| token usage | A local/runtime/gateway quantity observation | Yes, with source and finality |
| list-rate equivalent | A valuation from a bundled public rate snapshot | Yes |
| gateway estimate | A gateway-reported valuation | Yes, when imported |
| provider billed | A provider export or invoice-derived valuation | Only when that artifact is imported |
| subscription quota | A quota observation, not currency spend | Yes, if the source provides it |
| reconciliation coverage | Expected versus present evidence for a comparison | Yes |
| hard enforcement | A resource cannot be overspent outside the stated boundary | Not yet; only local experimental boundaries are permitted |
| actual cost | Provider-billed authority for the relevant account/time window | Only with a provider-billed charge |
| verified outcome | An explicitly recorded evidence item, such as a test exit | Yes, but never as proof a task was correct |

## Threat model

Forecost treats imported agent data, environment variables, repository-local
configuration, and hook input as untrusted.  The local ledger may reveal work
patterns even without content, so it is owner-only.  The product must resist
prompt/payload persistence, identifier/path disclosure, double-counted replay,
partial writes, stale reads at admission, and claims stronger than the evidence.

## Evidence gates

An adapter or command may move from experimental to supported only when it has:

- a content-free contract and synthetic conformance fixture;
- deterministic replay and idempotency coverage;
- documented identity, authority, finality, and failure boundaries;
- a receipt that makes missing or contradictory evidence visible; and
- an end-to-end test from input fixture through public output.

