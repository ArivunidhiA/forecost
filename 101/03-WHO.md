# Who is Forecost for?

## Primary users

### AI-agent engineers

They want to understand the resource shape of one run: branches, retries,
tokens, valuations, and outcome evidence. They are likely to use Run Lab,
receipts, capture/mark, and runtime adapters.

### Platform and infrastructure teams

They operate several runtimes or gateways and need to compare independent
sources without flattening them into one unreliable number. They care about
adapter contracts, reconciliation coverage, recovery, schema integrity, and
machine-readable output.

### FinOps or cost-conscious engineering teams

They need to know where a monetary claim came from and whether it is a list-rate
equivalent, a gateway estimate, a subscription quota, or provider-billed
evidence. Current unauthenticated local imports do not establish provider
origin. Forecost helps teams inspect declared provenance; it does not replace
invoicing.

### Privacy and security reviewers

They verify that economic observability does not become prompt collection. The
privacy canary, bounded schemas, local storage, threat model, and deletion
behavior are their primary surfaces. The current worktree repairs the reported
current-ledger cursor/log/scanner/purge paths, but legacy arbitrary metadata,
out-of-root state, and the same-UID boundary are exactly why an external
independent review is still required before release.

## People who operate the project

| Role | Start with | Typical responsibility |
| --- | --- | --- |
| Product lead | `01-WHAT`, `02-WHY`, `04-WHEN`, `13-CURRENT-STATE` | Protect the product boundary and validate demand |
| Core engineer | `06-HOW`, `07-ARCHITECTURE`, `08-DATA-MODEL` | Change ledger, receipts, CLI, or recovery safely |
| Adapter author | `08-DATA-MODEL`, `09-PRIVACY`, `12-TESTING` | Add a source without leaking content or breaking identity |
| Release engineer | `10-DEVELOPER-SETUP`, `12-TESTING`, `docs/release-process.md` | Validate wheels, matrices, metadata, and journeys |
| Security reviewer | `09-PRIVACY`, `SECURITY.md`, privacy tests | Review untrusted inputs, paths, persistence, and deletion |
| New contributor | This folder in order | Build a correct mental model before editing code |

## Who the software does not replace

- **Agent orchestrators:** Forecost observes/imports evidence; it does not plan
  or execute the user's workflow.
- **Providers:** it cannot issue or override a provider bill.
- **Trace systems:** it deliberately omits content needed for deep debugging.
- **Distributed budget services:** current controls are local and experimental.
- **Human reviewers:** a test exit or user mark is outcome evidence, not proof
  that the task was correct.

## Contributor expectation

A contributor is expected to preserve the project's claim discipline. New
features must state identity, source authority, finality, privacy behavior,
failure behavior, and storage boundary. “It works on my sample” is not enough
for an evidence system: replay, duplicates, late events, partial input, and
missing sources are normal cases that must be designed explicitly.
