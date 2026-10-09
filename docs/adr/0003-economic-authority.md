# ADR 0003: Economic authority is explicit

## Decision

Every valuation declares one authority: `billed`, `provider_estimate`,
`gateway_estimate`, `user_imported_claim`, `list_rate`,
`contract_allocation`, `subscription_quota`, or `unknown`.

`billed` is reserved for evidence admitted through a separately authenticated
provider profile. The current CLI has no such profile. An arbitrary JSON/CSV
file imported with `forecost reconcile import` is always
`user_imported_claim`, regardless of its filename, selected source, or fields
inside the file.

Schema v11 detects the fixed producer identities used by the historical local
file importer. It preserves each old journal row, appends an auditable
`user_imported_claim` correction, and supersedes the old active `billed`
projection. Other billed producers are not relabelled.

## Consequences

User-facing output may use "actual" only for authenticated `billed` evidence in
scope. `user_imported_claim` is independently useful evidence, but never proof
of provider origin. Canonical views select one authority per economic fact and
must never add alternatives together.
