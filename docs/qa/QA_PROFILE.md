# Forecost QA profile

**Profile version:** 1  
**Created:** 2026-08-09  
**Authority order:** `docs/product-contract.md`, public CLI behavior, canonical
schemas/contracts, `docs/capabilities.json`, then public documentation.

## Product and users

- **Product:** local Python CLI/library that creates content-free economic
  receipts for causal AI-agent runs.
- **Primary user:** engineer or platform team operating API-billed autonomous or
  graph-shaped agent work.
- **Primary job:** determine what a run consumed, what independent sources value
  it at, what graph behavior caused it, and how complete or contradictory the
  evidence is.
- **Non-products:** hosted service, generic observability UI, task-cost predictor,
  provider-side enforcement system, or source-code/transcript archive.

## Critical journeys

1. Install the base wheel in an empty environment and reach a meaningful
   synthetic receipt in under five minutes without network, credentials, or
   home-directory data.
2. Import a content-free offline provider/gateway/OTel export, reconcile it with
   local evidence, and render equivalent text, JSON, and Markdown receipts.
3. Inspect missing, late, ambiguous, contradictory, and superseded evidence
   without an estimate being promoted to billed authority.
4. Configure and self-test Claude hooks in an isolated fake configuration,
   observe lifecycle evidence, and diagnose missing/stale/broken integration.
5. Reserve, split, settle, release, expire, and recover graph-wide resources
   without violating conservation under concurrency, duplicate delivery, or
   process restart.
6. Upgrade a representative legacy database through backup and dry-run, retain
   evidence, and keep old authority/completeness claims conservative.
7. Verify privacy and ledger integrity after normal use and after deterministic
   tampering, truncation, reordering, duplication, and forking.

## Supported surfaces

- Public CLI entry point `forecost` and its current receipt-product commands.
- Python package public imports documented by the repository.
- Optional MCP, LiteLLM, Claude, OTel, OpenAI, and LangGraph adapters only to the
  degree declared by the capability matrix and installed extras.
- Text, JSON, and Markdown receipt artifacts.
- Local SQLite/filesystem state under an explicitly selected data root.

Legacy forecasting commands are compatibility-only and must not appear as the
current product. Live provider APIs, real accounts, publication, and hosted
services are outside this QA run.

## Data and privacy boundary

Forecost may persist typed content-free identity, lifecycle, graph topology,
meter quantities, valuations, source/provenance, finality, outcome codes,
resource state, and operational health. It must not persist prompts,
completions, tool payloads, source code, credentials, raw workspace/transcript
paths, baggage, tracestate, or unbounded external errors/identifiers.

## Oracles

- Canonical contract types and schema constraints are the structural oracle.
- Integer/decimal conservation and authority ordering are exact oracles.
- Deterministic Run Lab fixtures are expected-output oracles.
- Receipt format equivalence is an exact semantic oracle.
- Privacy sentinel absence and deterministic integrity classifications are exact
  security oracles.
- Resource conservation under a serialized reference model is the concurrency
  oracle.
- CLI exit status, stable JSON schema, and installed-artifact behavior are public
  interface oracles.

## Oracle gaps

- **UNKNOWN:** real-world identity fidelity across all current provider and
  runtime versions until maintainers supply representative sanitized fixtures.
- **UNKNOWN:** market demand, repeat use, and whether cross-source discrepancies
  change operator decisions until design-partner validation.
- **UNKNOWN:** provider-billed correctness for service tiers, negotiated pricing,
  credits, taxes, and adjustments not present in offline fixtures.
- **UNKNOWN:** cross-host or provider-side containment; it is not a supported
  claim and must not be inferred from local tests.
- **UNKNOWN:** Windows behavior unless a Windows runner validates the artifact.

## Release blockers

- Any content leak, credential read, raw path persistence, unsafe file mutation,
  destructive migration without backup, money float corruption, authority
  promotion, double count, resource conservation failure, non-idempotent replay,
  unverifiable integrity state, or broken base-wheel entry point.
- Any public claim stronger than the tested evidence boundary.
- Any critical journey that only passes from the source tree but fails from the
  built and installed artifact.
- Any supposedly offline test that requires network access, real credentials, or
  user home data.

## Evidence locations

- Initial frozen findings: `docs/qa/initial-findings.md`
- Final report: `docs/qa/final-report.md`
- Command/evidence log: `docs/qa/evidence/`
- Risk charter: `docs/qa/RISK_CHARTER.md`

## Final verdict vocabulary

The final report must end with exactly one of: **GO**, **GO WITH KNOWN RISK**,
**NO-GO**, or **BLOCKED**. Tests passing is evidence, not the verdict by itself.
