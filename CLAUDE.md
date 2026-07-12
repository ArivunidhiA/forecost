# forecost Development Guide

## What This Project Is
forecost is a local-first Python CLI/SDK that tracks and forecasts LLM API costs.
It uses an ensemble of three statistical methods (SES + Damped Trend + Linear Regression)
on daily spend data to predict total project cost, with anomaly detection and budget enforcement.
PyPI package, ~22 modules, 10+ test files, zero infrastructure dependencies.

## Architecture Rules
- All source code lives in forecost/ (flat layout, not src/)
- CLI commands are in forecost/commands/ — each is a thin wrapper calling core logic
- Core modules: db.py (SQLite + WriteQueue), pricing.py (80+ model prices),
  forecaster.py (ensemble engine), interceptor.py (httpx monkey-patching),
  tracker.py (public API), scope.py (heuristic analyzer), tui.py (optional Textual dashboard)
- Tests live in tests/ and tests/benchmarks/
- pyproject.toml uses hatchling build backend
- Entry point: `forecost = "forecost.cli:main"`

## Iron Rules (Never Violate These)
1. The interceptor must NEVER break the host application's HTTP requests.
   All tracking logic is wrapped in try/except. Real errors propagate, tracking errors are swallowed and logged to ~/.forecost/error.log.
2. calculate_forecast(save=False) is the default. Only the rich terminal `forecast` command
   (no --json, --brief, --output, or --exit-code) saves forecast rows.
3. No network calls for pricing data. All prices are hardcoded in FALLBACK_PRICING dict.
4. The WriteQueue worker thread has its OWN SQLite connection. Never share connections across threads.
5. .forecost.toml uses relative paths (path = "."). Never write absolute paths to config files.
6. Never use `except Exception: pass` — always log errors to ~/.forecost/error.log.
7. All cost calculations must handle edge cases: zero tokens, missing pricing data,
   unknown models, negative values, rate limit responses.

## Code Conventions
- Python 3.10+ compatibility. Type hints on all public APIs.
- Line length: 100 characters. Formatter/linter: ruff.
- Google-style docstrings on all public functions.
- Error messages must be actionable ("Expected API key in OPENAI_API_KEY env var" not "Key error").
- Follow existing code patterns before introducing new ones.
- No bare except clauses. Narrow to specific exception types.
- Rich library for terminal output. Click for CLI framework.

## Testing Rules
- Run `pytest tests/ -v --tb=short -m "not benchmark"` after every change
- The forecaster is the most important module — test accuracy with synthetic data
- The interceptor is the most dangerous module — test that it never breaks httpx
- Mock all HTTP calls in tests. Never make real API calls.
- Benchmarks in tests/benchmarks/ can be slower but must pass
- Property-based tests use Hypothesis (tests/test_property.py)
- Edge case tests in tests/test_edge_cases.py
- Use `tmp_path` and `monkeypatch` for test isolation
- Tests must be deterministic — no time.sleep() unless waiting for WriteQueue flush

## Module Dependency Order (no circular imports)
```
pricing.py       → (standalone, no internal imports)
db.py            → (standalone, sqlite3 only)
interceptor.py   → pricing, db
tracker.py       → pricing, db, interceptor
forecaster.py    → db (optionally statsmodels)
scope.py         → pricing
cli.py           → all of the above via commands/
tui.py           → db, forecaster (optional: textual, plotext)
```

## What NOT To Do
- Don't add a web dashboard or frontend
- Don't add database migrations (schema-less metadata JSON column handles extensibility)
- Don't add authentication or multi-user support
- Don't add real-time pricing fetches from the internet
- Don't add heavy ML dependencies (statsmodels is the ceiling)
- Don't import heavy optional deps (statsmodels, textual, plotext, numpy) at module level — lazy-import them inside the functions that need them

## Key Commands
```bash
pip install -e ".[dev]"                    # Install for development
pytest tests/ -v -m "not benchmark"        # Run all tests (skip benchmarks)
pytest tests/test_benchmarks.py --benchmark-only  # Run benchmarks only
pytest tests/ --cov=forecost --cov-report=term-missing  # Coverage
ruff check forecost/ tests/                # Lint
ruff format --check forecost/ tests/       # Format check
pyright forecost/                          # Type check
bandit -r forecost/ -ll                    # Security scan
xenon forecost/ -b B -m A -a A            # Complexity gate
forecost demo                             # See it working with sample data
```

## CI Pipeline
- Lint: ruff check + format, pyright, bandit, xenon
- Test: pytest with coverage (3.10-3.13 × ubuntu/mac/win matrix)
- Coverage gate: diff-cover --fail-under=85 on PRs
- Security: bandit + pip-audit + vulture
- Smoke: install from wheel, run --version, --help, demo

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

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

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.

## Multi-Agent Engineering Pipeline

This project uses a systematic fix pipeline with research → implement → verify phases.

### Agents
- **researcher**: Investigates complex issues, produces research reports in `.claude/research/`
- **fixer**: Implements fixes with tests, follows research reports
- **verifier**: Reviews fixes for correctness and completeness

### Progress tracking
All state is in `.claude/PROGRESS.md`. Always read it first when starting a session.

### Resume protocol
1. Read `.claude/PROGRESS.md`
2. Pick highest-priority 🔴 or 🟡 issue
3. If 🔴: research first, then fix. If 🟡: research done, go straight to fix.
4. Fix → verify → update PROGRESS.md → next issue
5. Before session ends: update PROGRESS.md with current state

### Reference documents
- `gaps/phase-1-audit-report.md` — Full codebase audit (1000+ lines)
- `gaps/Phase 1 audit, list.md` — Prioritized issue list with context and research