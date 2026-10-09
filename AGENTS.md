# Forecost agent handoff

This repository handoff file is no longer ignored, so it will travel with the
rest of this change when the maintainer commits it. Forecost 0.3 is an **unreleased experimental** local
economic-receipt system, not primarily the old calendar-spend forecaster. The
2026-08-13 red team placed the checkout under a P0 release hold. Do not merge,
tag, publish, enable production hooks, or use private transcripts/ledgers unless
the maintainer explicitly authorizes that separate action.

Read, in order:

1. `docs/status.md` — implemented truth and current release blockers;
2. `101/README.md` — beginner-to-contributor explanation;
3. `README.md` — current local workflow and product boundary;
4. `docs/product-contract.md` — normative intent, overridden by status where
   the current implementation violates it;
5. `docs/comparison.md` before changing matched-cohort comparison semantics;
6. the relevant ADR, source, and tests for the subsystem being changed.

The current ledger has two related but non-unified lanes: operational
`usage_events`/`postings`, and an append-only causal journal projected into
runs/spans/meter facts/charges/outcomes. Never assume an adapter populates both.
The current worktree has code-level remediations for the P0 findings: schema
v10 trace-scopes projected spans; receipt v2 uses explicit timing, preserves all
valuation groups, and reports named claim profiles; schema v11 demotes proven
historical arbitrary-file billing labels by append-supersession; canonical
SQLite uses `synchronous=FULL` and verified Backup API snapshots; current-path
cursor/log identities are keyed; owned-home scanning/purge coverage is expanded;
CI-only fail-closed behavior is explicit; and plugin runtime bootstrap is
disabled behind an exact owner-controlled launcher. Do not describe that work
as independently audited or release-ready.

Remaining publication blockers include the still-exported legacy SDK and
`costs.db` paths that can retain arbitrary raw names/paths/metadata; state
created at custom paths outside `FORECOST_HOME`; no authenticated/live provider
profile; no external independent privacy/security audit; public `main`/PyPI
still serving legacy code; no 30-run blinded validation or real-user demand
gate for the narrow comparison prototype; and the same-UID attacker outside
local integrity guarantees. See status and the current master checklist rather
than silently papering over them.

The comparison prototype has a deliberately narrow contract. Two run IDs are a
diagnostic that must always abstain. Only digest-bound arm manifests plus a
strict predeclared policy may qualify, and v1 is observational USD list-rate
equivalent only. Never relabel it as provider-billed, authenticated, causal
savings, or a completed product/field gate. Its local SHA-256 digests are not
signatures and manifest declarations are not independently authenticated.

Comparison decisions use a WAL-consistent in-memory Backup API copy, then verify
the journal chain and deterministically rebuild/hash-check journal-derived
projections. Broken journal/projection/rebuild evidence is invalid; more than
1,000,000 global journal rows abstains. V1 qualifies only final `delta` meters
with complete one-to-one valuation coverage, and any `reconciliation_batches`
row forces `RECONCILIATION_EVIDENCE_UNVERIFIED` because that state is outside
the derived inventory. Bootstrap seeding excludes caller-controlled labels.
CLI diagnostic IDs are validated before the ledger opens.

The CLI/MCP read path does not initialize/migrate schema or mutate Forecost
rows, but SQLite `mode=ro` may create or update WAL/SHM coordination sidecars.
Do not promise zero filesystem writes or change it to `immutable=1`; immutable
mode can miss committed WAL state. The fresh current-code Python 3.12 suite is
627 passed with one upstream MCP/Pydantic warning; that is internal regression
evidence, not an independent audit.

Use a new environment such as `.venv-review`; ignored local environments in a
shared checkout may have stale absolute shebangs. The maintained local checks
are:

```bash
python3.12 -m venv .venv-review
source .venv-review/bin/activate
python -m pip install -e ".[dev,forecast,llm,mcp]"
pytest tests/ -v --tb=short
ruff check forecost/ tests/
ruff format --check forecost/ tests/
pyright
mypy forecost/
xenon forecost/ -b B -m A -a A
bandit -r forecost/ -c pyproject.toml
pip-audit
```

Preserve unrelated worktree changes. Use `rg`/`rg --files` for targeted source
inspection when no repository graph is available. Use synthetic fixtures and
temporary `FORECOST_HOME` directories; never commit generated ledgers, secrets,
private transcripts, or local configuration.

<!-- code-review-graph MCP tools -->
## Optional MCP tools: code-review-graph

Some maintainer workspaces have a generated code-review graph and its MCP
tools. When those tools are actually installed and healthy, prefer them for
structural exploration before broad file scanning. The graph, `.mcp.json`, and
`.code-review-graph/` are intentionally local generated state and are not
required in a clone. Never block, guess results, or claim graph coverage when
the tools are unavailable; fall back to `rg`, focused reads, import tracing, and
tests.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow when the optional graph exists

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
