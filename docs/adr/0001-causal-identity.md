# ADR 0001: Content-free causal identity

## Decision

Use versioned conversation, trace, run, and span identities with parent links,
fan-in links, source sequence, and a stable idempotency key.  Validate W3C
trace/span identifiers when supplied; crosswalk nonconforming source IDs to a
deterministic opaque identifier.  Do not persist W3C baggage or tracestate.

## Consequences

Forecost can reconstruct branches, retries, and resumes without prompts or
payloads.  Source arrival order and SQLite row IDs are not causal ordering.

