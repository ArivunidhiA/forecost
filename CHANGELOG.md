# Changelog

## [0.2.0] - 2026-03-12

### Added
- **`forecost calc`** — Instant cost comparison across models. Paste a prompt (or `--file`), pick models, see cost per call and per 1,000 calls in a Rich table. Supports `--json` output.
- **`forecost price`** — Browse LLM pricing for all 80+ supported models. Filter by `--tier` (1/2/3) or get `--json` for programmatic use.
- **Dual-Mode Tracking (Tokens + Dollars)** — All CLI commands (`status`, `forecast`, `optimize`) now display both token counts and dollar costs. Subscription users see token burn rates alongside projections.
- **Model Capability Tiers** — Models classified into Tier 1 (Heavy), Tier 2 (Standard), and Tier 3 (Economy) in `pricing.py`. Used by `calc`, `price`, and `optimize` commands.
- **Tier-Based Optimization** — `forecost optimize` classifies tasks as Heavy/Standard/Light based on average token usage, and suggests alternatives within appropriate capability tiers instead of blindly picking cheaper models.
- **Multi-Source Data Schema** — `usage_logs` table now includes a `source` column (`api`, `cursor`, `claude`) preparing for IDE log ingestion in future releases. Existing databases are auto-migrated.
- **Language-Agnostic Scope Analysis** — `scope.py` now detects JS/TS SDK imports, scans `package.json`/`go.mod`/`Cargo.toml`, and reads `CLAUDE.md`/`.cursorrules` for better project understanding.
- 14 new tests (94 total, up from 80).

### Changed
- `get_daily_costs()` and `get_bucketed_costs()` now return 3-tuples `(period, cost, total_tokens)` instead of 2-tuples. Backward-compatible via `_insert_usage_logs_batch` accepting both 8- and 9-element tuples.
- `WriteQueue.put()` accepts an optional `source` parameter (defaults to `"api"`).
- Forecast JSON output includes `total_tokens` field.
- Status command now shows token count in the one-line summary.
- `asyncio.iscoroutinefunction` replaced with `inspect.iscoroutinefunction` to fix Python 3.16 deprecation warning.

### Fixed
- `asyncio.get_event_loop()` deprecation in tests (replaced with `asyncio.run()`).

## [0.1.1] - 2026-03-12

### Fixed
- Added `pytest-asyncio` to dev dependencies for async test support in CI.
- Set `asyncio_mode = "auto"` in pytest configuration.

## [0.1.0] - 2026-03-12

### Added
- Initial release: cost tracking, ensemble forecasting, CLI commands, TUI dashboard, local API server, pricing database with 80+ models.
