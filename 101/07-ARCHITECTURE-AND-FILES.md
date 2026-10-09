# Architecture and file map

## Top-level map

```text
forecost/
├── forecost/             Python package
│   ├── adapters/         Source-specific ingestion and mapping
│   ├── commands/         Click command implementations
│   ├── core/             Paths, error logging, recovery spools
│   ├── estimate/         Shadow estimator and calibration
│   ├── hooks/            Claude hook fast path and lifecycle handlers
│   ├── ledger/           Canonical database, contracts, receipt kernel
│   ├── mcp/              Optional read-only MCP server
│   ├── policy/           Local TOML rules and evaluation
│   ├── comparison.py     Strict read-only matched-cohort evaluator
│   ├── evidence_profiles.py  Named evidence obligations and scoring
│   ├── cli.py            Lazy command registry
│   ├── lab.py            Deterministic synthetic scenarios
│   ├── reconciliation.py Offline graph/economic reconciliation
│   └── resources.py      Experimental single-host envelopes
├── tests/                Synthetic tests and benchmarks
├── docs/                 Contracts, ADRs, status, QA, release evidence
├── experiments/calib/    Reproducible estimator backtest
├── examples/litellm/     LiteLLM callback example
├── plugin/               Claude Code plugin package
├── scripts/              Release and benchmark tooling
├── 101/                  Beginner onboarding documentation
├── pyproject.toml        Package, dependencies, tools, entry points
├── CHANGELOG.md          Version history and unreleased changes
└── README.md             Public entry point
```

## Current core by responsibility

| Responsibility | Primary files |
| --- | --- |
| CLI registration and lazy loading | `forecost/cli.py` |
| Typed ingestion/privacy contracts | `forecost/ledger/contracts.py`, `forecost/adapters/base.py` |
| SQLite connection and schema | `forecost/ledger/db.py`, `forecost/ledger/schema.py` |
| Installation-keyed local identities | `forecost/core/local_identity.py` |
| Operational usage writes | `forecost/ledger/sink.py`, `forecost/ledger/writer.py`, `forecost/ledger/state_store.py` |
| Operational summaries | `forecost/ledger/queries.py` |
| Journal and deterministic projection | `forecost/ledger/evidence.py` |
| Graph receipt construction | `forecost/ledger/receipts.py` |
| Named claim profiles | `forecost/evidence_profiles.py` |
| Journal/receipt integrity | `forecost/ledger/integrity.py` |
| Claude transcript ingestion | `forecost/adapters/claude_code.py` |
| Claude hook execution | `forecost/hooks/fastpath.py`, `handlers.py`, `state.py` |
| LiteLLM callback/outbox | `forecost/adapters/litellm_hook.py`, `outbox.py` |
| OTel and framework mappings | `forecost/adapters/otel.py`, `frameworks.py`, `causal.py` |
| Adapter capability protocol | `forecost/adapters/protocol.py` |
| Offline reconciliation | `forecost/reconciliation.py` |
| Matched-cohort comparison | `forecost/comparison.py`, `forecost/commands/compare_cmd.py` |
| Resource envelopes | `forecost/resources.py` |
| Synthetic scenarios | `forecost/lab.py` |
| Shadow estimation | `forecost/estimate/` |
| Optional MCP | `forecost/mcp/server.py`, `forecost/mcp_launcher.py` |

## CLI architecture

`pyproject.toml` installs two console scripts:

- `forecost` calls `forecost.cli:main`;
- `forecost-hook` calls `forecost.hooks.fastpath:main`.

`forecost/cli.py` lazy-loads command modules. This keeps base startup small and
prevents optional or legacy dependencies from breaking current commands. The
optional MCP server is deliberately launched with
`python -m forecost.mcp_launcher` after installing the `mcp` extra.

The source Claude plugin launcher is stricter than ordinary console discovery:
it executes only `$CLAUDE_PLUGIN_DATA/venv/bin/forecost-hook` after owner, mode,
and symlink-component checks and never falls back to `PATH`. Its bootstrap script
does not install packages at runtime. That repair does not create a supported
production installer; plugin enablement remains release-held.

## Adapter architecture

Adapters should depend on the bounded internal contracts rather than writing
arbitrary source objects to SQLite. A new adapter normally needs:

1. a protocol/capability declaration;
2. deterministic synthetic fixtures;
3. identity, cursor, duplicate, finality, and failure rules;
4. privacy/conformance coverage;
5. an end-to-end public output proving what the adapter contributes.

Optional third-party SDKs must not import during base CLI startup.

## The legacy island

These modules belong primarily to the forecast-era product:

- `forecost/db.py` — old `costs.db` access;
- `forecost/tracker.py` and `interceptor.py` — legacy tracking/HTTPX interception;
- `forecost/forecaster.py` — optional statistical calendar forecasting;
- `forecost/pricing.py` — legacy pricing catalog;
- `forecost/scope.py` — legacy project-scope analysis;
- `forecost/tui.py` — legacy terminal dashboard;
- forecast-era files in `forecost/commands/`.

They remain for v0.2 compatibility and are routed through `forecost legacy`.
Do not make a current command depend on `costs.db`, and do not infer current
product direction from these modules. Backward-compatible Python symbols are
still exported, however, and legacy project creation/tracking can persist raw
project names, paths, and arbitrary metadata in `costs.db`; removing or
constraining that surface is a publication blocker.

## Documentation hierarchy

- `docs/status.md`: latest implemented/release state; current blockers override
  normative contracts when describing behavior. Internal test/audit evidence is
  not an independent external review.
- `docs/capabilities.json`: machine-readable current capability/hold truth.
- `docs/product-contract.md`: normative product laws and intended claims.
- `docs/architecture.md`: concise technical architecture.
- `docs/comparison.md`: strict comparison inputs, evidence gates, decisions,
  exit codes, and trust boundary.
- `docs/adr/`: decisions for identity, meter/charge separation, authority,
  receipt versioning, resources, privacy, and legacy retirement.
- `docs/qa/final-report.md`: historical 2026-08-09 packaged QA; superseded for
  release decisions by the 2026-08-13 status/red team.
- `docs/completion-checklist.md`: historical implementation record with checked
  claims that the later red team reopened.
- `docs/research/2026-08-13-master-product-launch-checklist.md`: current proposed
  no-release gates and conditional execution plan.
- `docs/master-checklist.md`: original plan; unchecked boxes are not current
  implementation status.

Always read the repository's committed `AGENTS.md` before agent-assisted work.
It describes the code-review knowledge graph as an optional local accelerator;
if those tools are unavailable, use its targeted source-inspection fallback.
