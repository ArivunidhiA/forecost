# ADR 0003: Economic authority is explicit

## Decision

Every valuation declares one authority: `billed`, `provider_estimate`,
`gateway_estimate`, `list_rate`, `contract_allocation`, `subscription_quota`,
or `unknown`.

## Consequences

User-facing output may use "actual" only for `billed` evidence in scope.

