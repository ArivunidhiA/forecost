# Architecture and product laws

Forecost is an independent, local receipt for AI-agent work. It deliberately
keeps physical usage facts separate from valuations so a provider-reported cost,
a pricing-table calculation, and a subscription-quota debit can coexist without
being summed accidentally.

## Data flow

1. A pull adapter reads a harness's append-only usage source, or a push adapter
   receives a gateway callback.
2. The adapter emits a content-free `UsageEvent` with a stable source identity.
3. The sink resolves workspace/session identity and atomically commits the event
   with one or more provenance-labeled postings.
4. Canonical queries select one appropriate posting per event; they never add
   competing valuations of the same event.
5. Reconciliation compares meters. Policy reads only reliable canonical spend
   for hard actions. Estimation and anomaly flags remain shadow-only.

## Non-negotiable invariants

- **Content-free:** no prompt, completion, tool payload, or file content reaches
  the ledger, recovery queue, or error log.
- **One response, one event:** retries and multi-block responses deduplicate on
  stable provider/harness identity.
- **Atomic receipt:** an event without its required postings is never visible.
- **No silent loss:** rejected queues, failed drains, torn input, and failed
  recovery remain observable and retryable; failed batches use immutable spools
  and replay their original postings without re-pricing.
- **No false authority:** guessed prices are labeled and cannot hard-deny work.
- **Fail-open hooks:** instrumentation failure never breaks the host agent.
- **Single private home:** all persistent state follows `FORECOST_HOME` and is
  owner-only where the platform supports permissions. A relocated, existing
  directory is never chmodded or purged without a Forecost ownership marker.

## Trust boundaries

Claude Code transcripts and LiteLLM callbacks are untrusted input. Repository
policy is also untrusted unless the user opts in. Plugin lifecycle hooks never
install packages; installation of the pinned release is an explicit user action.
Publishing requires source
quality checks, artifact inspection, supported-Python smoke tests, and version
agreement across package, plugin, changelog, and tag.

See [the current audit](audit-1.md) for the ranked hardening backlog and
`experiments/calib/VERDICT.md` for why predictions are not displayed.
