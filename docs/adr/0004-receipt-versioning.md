# ADR 0004: Receipts are versioned evidence artifacts

## Decision

Receipt JSON uses a schema version, canonical deterministic ordering, explicit
evidence state, provenance, finality, discrepancy, outcome, and integrity
fields.  Unknown future fields are retained only in the raw journal envelope;
unsupported schema versions fail clearly.

Receipt v2 removes a public global-completeness claim. Named claim profiles
publish independent completeness, freshness, and contradiction axes, their
predeclared denominator, and every unmet obligation. The old projection-wide
heuristic remains only as `legacy_projection_state` for migration diagnostics.

Execution timing is populated only by explicit start/end evidence or an
explicitly reported duration. Occurrence time records when an event happened;
observation time records when evidence was seen. They are never interpreted as
span endpoints. Aggregate wall timing requires a complete explicit interval for
every span. `service` is the union of non-wait intervals, `wait` is the union of
`queue_wait` intervals, and `elapsed` is the earliest-start/latest-end envelope,
including gaps. Service and wait can overlap and must not be added. The present
parent/fan-in edges do not state scheduling-dependency semantics, so a
non-trivial `critical_path` is withheld; it is populated only for the trivial
single-span graph. A cycle marks path timing invalid while leaving the directly
observed interval unions visible.

Receipt schema remains v2 because this correction preserves existing field
names and types, additively exposes supersession assessment, and removes
unjustified values from an unreleased schema.
Built-in claim profiles remain version 1 because their obligations, source
roles, finality rules, closure rules, and denominators did not change. Profile
versioning covers that predeclared contract; the evaluator fix no longer treats
an absent freshness SLA as proof of freshness. Adding an SLA or changing an
obligation requires a profile-version bump.

An obligation with `max_age_seconds = null` now reports freshness `unknown`,
even when its completeness obligation is satisfied. Structural signals use the
raw source observation timestamps from the journal, never receipt assessment
time. Receipt `as_of` is at least as late as every signal evaluated. A lifecycle
regression after a terminal observation is surfaced as structural
contradiction even when projection ordering selects a superficially closed row.
A cycle in parent/fan-in causal edges likewise contradicts structural closure;
it cannot coexist with a clear/complete structural assessment.
An unresolved parent or fan-in target is absence rather than contradiction: it
withholds the branch-closure obligation, making structural completeness partial
and contradiction unknown. A missing predeclared source has the same effect;
the sources-present list cannot close a scope that explicitly expected more.

Outcome rows also remain append-only. Assessment uses the active set after
valid explicit `supersedes_evidence_id` edges. An edge is valid only when its
target exists in the same run at a lower journal sequence. Forward, missing,
cross-run, cross-role, and self references remain active and contradict the
outcome profile. In particular, a human mark cannot retire independent test or
CI evidence. Active `good` and `bad` statuses contradict both outcome
obligations across evidence roles; `partial` does not by itself oppose a
decisive status. A valid explicit supersession retires only its referenced row
from assessment and selection, not from history. Test/build progressions still
need case-attempt identity to distinguish reruns precisely.

Charge supersession follows the same earlier-same-run rule and must stay within
one economic fact, currency, and line item. An invalid `supersedes_charge_id`
cannot hide its target; both remain active, the economic assessment is
contradictory, and valuation-group output exposes the invalid edge.

All active competing valuations are retained in `valuation_groups`. Exactly
one canonical valuation is selected per economic fact/currency/line item using
the declared authority ordering and deterministic tie-break, and alternatives
are explicitly non-additive.
