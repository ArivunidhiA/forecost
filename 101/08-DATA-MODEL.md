# Data model and vocabulary

This guide uses a store receipt analogy. The analogy is imperfect, but it makes
the key separations easier to remember.

## Identity and topology

| Term | Meaning |
| --- | --- |
| Conversation | Continuity across related work |
| Trace | Portable distributed identity when one exists |
| Run | The boundary of one workflow receipt |
| Span | One causal operation inside a run |
| Span key | Internal deterministic hash of trace + span; prevents cross-trace span-ID collisions |
| Parent span | The operation that directly caused another operation |
| Link | A non-tree dependency such as fan-in |
| Attempt | A particular try, distinct from a retry |
| Branch | A structural path through parallel or conditional work |
| Source sequence | A producer's ordered replay boundary |
| Idempotency key | Identity that makes replay safe and detects conflicting reuse |

## Meter facts: what quantity was observed?

A meter fact is like “three items” or “250 grams” on a store receipt. It is a
quantity, not a price. In Forecost that might be input tokens, output tokens,
calls, or another approved bounded measurement.

Meter facts retain source, aggregation/finality, and causal association when
known. A runtime count does not automatically become billed truth.

## Charges and postings: what did one source say it was worth?

A valuation attaches money, quota, or allocation meaning to an economic fact.
The operational lane calls these postings; the graph receipt lane calls them
charges. Both preserve the principle that several valuations can describe the
same consumption.

Examples:

- public tokens × bundled rate = list-rate equivalent;
- LiteLLM `response_cost` = gateway estimate;
- an authenticated provider profile = provider-billed evidence; the current
  CLI has no such profile, and arbitrary local-file import is always a declared
  user-imported claim;
- a contract allocation = an internal allocation, not a provider bill;
- subscription quota = quota evidence, not necessarily currency spend.

## Authority: who said the number?

Authority describes the source's economic role. It is separate from the numeric
amount. Current receipt authority categories include provider billed, provider
estimate, gateway estimate, user-imported claim, list-rate equivalent, contract
allocation, subscription quota, and unknown.

“Canonical” does not mean objectively true. It means Forecost selected one value
according to explicit rules for a particular view. The ledger preserves
alternatives. Receipt v2 exposes every active valuation group plus the selected
canonical value and selection reason without summing competing alternatives.

## Finality: how settled is it?

A highly authoritative source can still be provisional, and a final observation
can have weak authority. Forecost therefore stores finality separately. Late
evidence creates a new observation and may supersede an earlier reconciliation;
it does not rewrite the historical journal entry that an old receipt used.

## Outcomes: what external fact was recorded?

`forecost capture` can record a bounded test/build exit and Git identity.
`forecost mark` can record an explicit user outcome. These are evidence that a
command exited zero or a user supplied a label. They are not proof that the
agent's work is correct.

Active `good` and `bad` statuses contradict the outcome profile across evidence
roles; `partial` alone does not oppose a decisive result. An outcome with
`supersedes_evidence_id` removes only an existing earlier same-role target in
the same run from the active assessment/selection set; it does not delete
historical evidence. A human mark cannot retire test/CI evidence. Forward,
missing, cross-run, cross-role, and self references are invalid, remain active,
and contradict the profile. Test/build facts still need case-attempt identity.
Charge supersession additionally requires the same economic fact, currency, and
line item; invalid edges make economic evidence contradictory.

## Reconciliation: how do claims compare?

Reconciliation is not summation. It records:

- the sources expected and present;
- the time or run scope;
- exact, aggregate, ambiguous, or unmatched evidence;
- expected and observed totals;
- residual and tolerance;
- freshness/finality;
- supersession by later evidence.

If a local list-rate equivalent says $1.10 and an authenticated provider export says $1.04,
Forecost preserves both and reports the difference. It does not report $2.14.

## Timing: when is a duration known?

Arrival/observation time is not execution duration. Receipt v2 accepts an
explicit span interval or a source-reported duration with a named semantic and
producer. With complete explicit intervals, `service` is the union of non-wait
intervals and `wait` is the union of queue-wait intervals. Each avoids nested
and parallel double counting, but they can overlap each other and are not
additive. `elapsed` is the earliest-start/latest-end envelope, including gaps.
Because current parent/fan-in edges are structural rather than typed scheduling
dependencies, a non-trivial `critical_path` is `null`; the only populated case
is one span with one unambiguous interval. Cycles invalidate path timing while
the directly observed unions remain visible.

## Claim profiles: complete for what?

“Complete” is not a global property. A versioned profile declares its
obligations and denominator before evidence is evaluated. Built-in profiles
cover structural, economic-estimate, provider-billed, outcome, and CI claims.
Each reports completeness, freshness, and contradiction independently, with
the satisfied count, unmet obligations, reason codes, and assessment time. An
arbitrary user import cannot satisfy the provider-billed profile.

`max_age_seconds: null` means that a profile declares no freshness SLA. It
therefore evaluates to freshness `unknown`, not `fresh`, even when every
completeness obligation is satisfied. Structural evidence retains its actual
journal observation time, and a later lifecycle regression is contradictory.
So is a cycle in the graph's declared parent/fan-in causal edges; closure cannot
be both clear and cyclic.
Missing parent or fan-in targets are evidence gaps, not conflicts: they make the
structural closure obligation partial and leave contradiction unknown.
So does a missing predeclared source in `sources_expected`; observed topology
cannot prove closure for an explicitly broader evidence scope.
The current built-ins stay profile version 1 because this evaluator correction
does not change their obligations or denominators; adding an SLA would require
a new profile version.

## Comparison: when are two arms really matched?

A comparison arm is a manifest that binds a frozen dataset/task set, one complete
model+harness+policy configuration, an exact source denominator, and a sorted
case roster. Each case binds its pair, distinct attempt and run, verifier,
predeclared test/build outcome evidence, receipt digest, and tariff digest. A separate policy
predeclares the same roster and the economic/outcome thresholds.

Comparison v1 admits only receipts whose meter facts are all final `delta`
observations and whose selected USD `list_rate` groups cover those facts
one-to-one, plus active decisive `test_exit` or `build_exit` evidence. It
requires at least 30 pairs and reports deterministic paired-bootstrap confidence
bounds. The seed uses only a fixed protocol label and sorted numeric paired
observations, so renaming opaque case/run/manifest labels cannot change the
resampling decision.

Before reading evidence, the engine makes one WAL-consistent in-memory copy,
checks the journal chain, and deterministically rebuilds/hash-compares the
journal-derived projections. Broken chain/projection/rebuild evidence is
invalid; a global journal above 1,000,000 rows causes abstention. Reconciliation
batches are not journal-derived in v1, so any batch also forces abstention rather
than being treated as verified. These bindings prevent Forecost from calling
two unrelated totals “savings.” They do not authenticate the manifest or prove
causal assignment; the result is observational.

The simple diagnostic for two valid existing runs has no manifests and therefore always abstains.
See the complete [comparison contract](../docs/comparison.md).

## Integrity

The journal uses a local SHA-256 integrity chain and receipt snapshots use
deterministic digests. These mechanisms help classify unexpected local changes
and prove stable serialization. They are not signed receipts, remote
attestation, or protection against the same local user deliberately replacing
the data and metadata.

Canonical SQLite uses `synchronous=FULL`. Before schema migration, Forecost uses
SQLite's Backup API to create a verified standalone snapshot that includes
committed WAL pages; partial or invalid snapshots are removed. This improves the
documented local durability path but is not a universal no-data-loss guarantee.

## Monetary representation

Money is stored deterministically in integer micros where applicable, avoiding
floating-point accounting drift. Pricing provenance must be retained so a
historical valuation can be audited rather than silently changing when the
bundled pricing table changes.
