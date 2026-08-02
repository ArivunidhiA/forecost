# ADR 0004: Receipts are versioned evidence artifacts

## Decision

Receipt JSON uses a schema version, canonical deterministic ordering, explicit
evidence state, provenance, finality, discrepancy, outcome, and integrity
fields.  Unknown future fields are retained only in the raw journal envelope;
unsupported schema versions fail clearly.

