# forecost Development Guide

## What This Project Is
forecost is a local-first Python CLI tool that forecasts LLM API costs.
It uses adaptive exponential smoothing (upgrading to a 3-model ensemble)
on daily spend data to predict total project cost.

## Architecture Rules
- All source code lives in forecost/ (flat layout, not src/)
- CLI commands are in forecost/commands/ — each is a thin wrapper calling core logic
- Core modules: db.py (SQLite), pricing.py (static prices), forecaster.py (ensemble),
  interceptor.py (httpx patching), tracker.py (public API), scope.py (heuristic analyzer)
- Tests live in tests/ and tests/benchmarks/
- pyproject.toml uses hatchling build backend

## Iron Rules (Never Violate These)
1. The interceptor must NEVER break the host application's HTTP requests.
   All tracking logic is wrapped in try/except. Real errors propagate, tracking errors are swallowed.
2. calculate_forecast(save=False) is the default. Only the explicit `forecast` command saves.
   Status, serve, and JSON output do NOT save forecast rows.
3. No network calls for pricing data. All prices are hardcoded in FALLBACK_PRICING dict.
4. The WriteQueue worker thread has its OWN SQLite connection. Never share connections across threads.
5. .forecost.toml uses relative paths (path = "."). Never write absolute paths to config files.

## Testing Rules
- Run pytest tests/ -v after every change
- The forecaster is the most important module — test accuracy with synthetic data
- The interceptor is the most dangerous module — test that it never breaks httpx
- Mock all HTTP calls in tests. Never make real API calls.
- Benchmarks in tests/benchmarks/ can be slower but must pass

## What NOT To Do
- Don't add a web dashboard or frontend
- Don't add database migrations (schema-less metadata JSON column handles extensibility)
- Don't add authentication or multi-user support
- Don't add real-time pricing fetches from the internet
- Don't add heavy ML dependencies (statsmodels is the ceiling)
- Don't use except Exception: pass — always log errors to ~/.forecost/error.log

## Key Commands
pip install -e ".[dev,forecast]"   # Install for development
pytest tests/ -v                    # Run all tests
pytest tests/benchmarks/ -v         # Run accuracy benchmarks
ruff check forecost/ tests/           # Lint
forecost demo                         # See it working with sample data
python -m build                     # Build for PyPI
