# Forecost status — 2026-08-09

<!-- package-version: 0.3.0 -->
<!-- capability-schema-version: 1 -->
<!-- product-contract-version: 1.0 -->

## Current product state

Forecost 0.3.0 is an **experimental local economic-receipt product**. Its
canonical store is `~/.forecost/ledger.db`; receipts retain content-free causal,
meter, valuation, authority, finality, and outcome evidence. Deterministic Run
Lab fixtures and offline imports can exercise the product without accounts,
credentials, transcript content, or network access.

The separate `~/.forecost/costs.db` file belongs to the retired v0.2 calendar
forecaster. It is reachable only through `forecost legacy …` or the explicit
`forecost migrate` copy path. Legacy commands have no hidden root aliases,
`init --smart` has been removed, and the unauthenticated loopback HTTP server has
no CLI registration and is not a current API.

## Supported claims

- Text, JSON, Markdown, CLI, and optional MCP receipts are views of canonical
  ledger evidence, not provider invoices.
- Imported provider or gateway amounts retain their source-specific authority;
  list-rate equivalents remain independent valuations.
- Claude Code and LiteLLM integration is experimental observation. Claude hooks
  are fail-open and cannot claim provider-side or distributed containment.
- OpenAI Agents and LangGraph support is currently an offline mapping contract
  proven against local fakes; it does not imply an installed SDK or live runtime.
- Resource envelopes are experimental, single-host controls. Their published
  boundary does not imply a bounded provider-side overrun; maximum overrun
  outside the local transaction boundary is not bounded.
- Explicit test/build exits and user marks are outcome evidence, never proof that
  a task is correct.

## Shipped interface boundary

- The root CLI lists current receipt-product commands and prints each command's
  store boundary. Retired commands require the `legacy` namespace.
- The optional MCP module is read-only and exposes only
  `forecost_list_runs` and `forecost_get_receipt` against `ledger.db`. The base
  wheel intentionally has no `forecost-mcp` console entry point; after installing
  `forecost[mcp]`, use `python -m forecost.mcp_launcher`.
- `docs/capabilities.json` is the machine-readable authority for adapter,
  interface, store, and claim boundaries. The release validator checks its
  version and required contract fields against this status file and package
  metadata.

## Not claimed

Live provider billing APIs, provider-billed authority without an imported
artifact, complete graph identity across every runtime, verified task
correctness, distributed enforcement, task-cost forecasting, and a hosted
control plane are not part of this release.

## Publication state

The 0.3.0 changelog remains `Unreleased`. No PyPI release, GitHub release, tag,
merge, announcement, or real-data migration is implied by this branch. Those
remain founder-controlled actions after packaged-product QA.
