# ADR 0001: Trace-scoped causal identity

## Decision

Use versioned conversation, trace, run, and span identities with parent links,
fan-in links, source sequence, and a stable idempotency key.  Validate W3C
trace/span identifiers when supplied; crosswalk nonconforming source IDs to a
deterministic opaque identifier.  Do not persist W3C baggage or tracestate.

`span_id` is only unique inside a trace. Projection tables therefore join on
`span_key = SHA-256(normalized_trace_id || normalized_span_id)` and retain the
source `span_id` for display/interchange. Parent, retry, fan-in, meter, charge,
reconciliation, and receipt joins use `span_key`. A run ID must map to exactly
one conversation/trace and a trace-scoped span must map to exactly one run.

Schema v10 rebuilds projections from the append-only journal. Reuse of the same
span ID in different traces is repaired without conflation. If one run maps to
multiple trace owners, or one trace-scoped span maps to multiple run owners,
migration fails and leaves the v9 database/journal intact; it does not guess.

## Consequences

Forecost can reconstruct branches, retries, and resumes without prompts or
payloads.  Source arrival order and SQLite row IDs are not causal ordering.
Legacy SQL or integrations that join on bare `span_id` are incompatible with
receipt v2 and must be updated to use `span_key` or `(trace_id, span_id)`.
