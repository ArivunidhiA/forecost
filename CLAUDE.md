# Forecost development guide

## Read this first

Forecost 0.3 is an unreleased local economic-receipt system for AI-agent runs
with a content-minimizing intended contract. It is not primarily the old
calendar-spend forecaster. A 2026-08-13 red team found raw-path/log, receipt,
authority, and durability P0 defects. The current worktree contains internal
remediations for those current-ledger paths, but release remains held for the
remaining legacy, live-validation, external-review, and distribution gates in
`docs/status.md`.
Start with:

1. `AGENTS.md` for repository tool instructions;
2. `101/README.md` for the complete onboarding path;
3. `docs/status.md` and `docs/capabilities.json` for current claim boundaries;
4. `docs/product-contract.md` for intended product laws;
5. the relevant ADR and tests before changing a subsystem.

The forecast-era code remains only for compatibility under `forecost legacy`
and uses the separate `costs.db`. Current receipt code uses `ledger.db`.

## Current architecture

The Python package lives in `forecost/` and supports Python 3.10–3.13 in CI.
Click commands are lazy-loaded from `forecost/commands/` through
`forecost/cli.py`.

`ledger.db` contains two related but not fully unified evidence lanes:

- operational usage: `usage_events`, separate valuation `postings`, policy,
  calibration, and operational summaries;
- causal receipt kernel: append-only journal observations projected into runs,
  spans, links, meter facts, charges, outcomes, receipts, and reconciliation.

Claude Stop/lifecycle hooks can feed both. Manual Claude ingestion and LiteLLM
feed operational usage; offline OTel-style import feeds the receipt journal.
Never imply an adapter produces a complete graph unless its end-to-end tests
prove that path.

Primary modules:

- `forecost/ledger/`: contracts, schema, writes, journal, projections,
  receipts, queries, integrity;
- `forecost/adapters/`: Claude, LiteLLM, OTel, framework mappings, conformance;
- `forecost/hooks/` and `forecost/policy/`: local fail-open Claude lifecycle and
  policy behavior;
- `forecost/estimate/`: shadow-only estimator/calibration;
- `forecost/reconciliation.py`: offline independent evidence comparison;
- `forecost/resources.py`: experimental single-host envelopes;
- `forecost/mcp/`: optional read-only two-tool MCP interface;
- `forecost/db.py`, `tracker.py`, `interceptor.py`, `forecaster.py`, `scope.py`,
  and `tui.py`: primarily legacy compatibility.

## Product laws

1. Evidence before advice.
2. Prompts, completions, tool payloads, source code, credentials, and raw paths
   are forbidden from current-ledger persistent state; add all-artifact privacy
   tests with every relevant change. The unsupported legacy `costs.db` can hold
   project names, paths, and legacy metadata and is outside this stronger
   contract until it is removed or migrated.
3. Preserve causal identity before aggregation.
4. Quantities and valuations are different facts.
5. Provider-billed, gateway, list-rate, quota, and unknown authorities remain
   explicit; competing values are not summed.
6. Local controls make only local, fail-open claims and cannot promise
   provider-side or distributed containment.
7. Late evidence supersedes; it does not rewrite the historical journal.
8. Text, JSON, Markdown, and MCP output must agree semantically.

## Engineering rules

- All public APIs use type hints; keep Python 3.10 compatibility and 100-column
  formatting.
- Optional/heavy SDKs must stay off the base startup import path.
- Use bounded typed fields at adapter boundaries; never persist arbitrary source
  dictionaries or error strings.
- Identity, cursor advancement, replay, partial input, late evidence, finality,
  failure, and recovery require explicit tests.
- SQLite writes sharing a process connection must use the repository transaction
  discipline. Schema changes use the forward-only migration ladder and need
  upgrade tests.
- Hooks and interceptors must not break the host application. Log bounded errors
  instead of swallowing them silently.
- Repository-local policy is untrusted unless the user explicitly sets
  `FORECOST_TRUST_PROJECT_POLICY=1`.
- Do not add hosted infrastructure, live pricing/provider ingestion, hard
  distributed-control claims, or user-facing prediction without changing the
  product contract and satisfying its evidence gates.
- Preserve unrelated worktree changes and use synthetic fixtures, never private
  transcripts or databases.

## Development commands

```bash
python3.12 -m venv .venv-review
source .venv-review/bin/activate
python -m pip install -e ".[dev,forecast,llm]"

pytest tests/ -v --tb=short
ruff check forecost/ tests/
ruff format --check forecost/ tests/
pyright
xenon forecost/ -b B -m A -a A
bandit -r forecost/ -c pyproject.toml
pip-audit
```

Install `.[mcp]` before MCP tests or launch the optional server with
`python -m forecost.mcp_launcher`. Use the installed `forecost` console script;
`python -m forecost.cli` is not the product launcher.

Safe first workflows:

```bash
forecost lab demo
forecost lab chaos
forecost doctor
```

Use an absolute temporary `FORECOST_HOME` or explicit Run Lab ledger when
strictly isolating local developer data.

## Legacy rules

Legacy HTTPX interception must remain fail-open, use its own `costs.db` write
discipline, and never become a hidden dependency of current commands. The old
forecast, TUI, server, scope, pricing, and tracker behavior is unsupported
compatibility—not the roadmap.

The old unauthenticated loopback server and removed `init --smart` upload path
must not be re-registered. Legacy observations can be copied only through the
explicit migration command and must not gain stronger identity, authority, or
finality.
