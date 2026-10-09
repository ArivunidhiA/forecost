# Changelog

> **2026-08-13 publication hold:** the current worktree contains internal
> remediations for the receipt-v2, trace identity, timing, evidence-profile,
> import-authority, cursor/log privacy, known-root purge, durability, explicit-CI
> fail-closed, and launcher defects found by the red team. They have not had an
> external security/privacy review or live design-partner validation. Legacy SDK
> state, state deliberately placed outside `FORECOST_HOME`, authenticated
> provider billing, public package/repository identity, and real-runtime claims
> remain release blockers. The feature list below is implementation scope, not a
> publication claim. See `docs/status.md`.

## [0.3.0] - Unreleased

Repositioning: Forecost is now an experimental local, content-minimizing **economic
receipt** for AI-agent runs. It preserves causal and meter evidence, keeps
independent valuations separate, and makes disagreement and missing evidence
visible. Claude controls are fail-open and do not claim provider-side or
distributed containment. The retired calendar-spend forecaster remains only
under the explicit `forecost legacy` compatibility namespace.

### Changed
- Legacy SDK/`costs.db` now stores an installation-keyed pseudonym instead of the raw project
  path, reduces project names to a basename, and keeps only bounded scalar metadata
  (identifier-like keys; numbers, booleans, short token strings). Rows written by
  earlier versions keep their raw values until the user purges them.

### Added
- **`forecost ingest`** — pull Claude Code JSONL transcripts into the ledger
  (idempotent and resumable; cursor identities are installation-keyed and
  replacement-aware, while transcript content is opened locally but excluded
  from the current ledger contract).
- **`forecost ledger status|by-workspace`** — spend views with a `--basis`
  selector (canonical / pricing_table / source_reported).
- **`forecost reconcile`** — internal consistency check plus a source-reported
  vs pricing_table cross-check on shared events.
- **`forecost burn`** — trailing burn rate projected against active budgets.
- **`forecost calibration`** — the published accuracy record for the shadow
  estimator.
- **`forecost pricing-audit`** — reports models priced by guess and table
  freshness.
- Claude Code hook adapter (`forecost-hook`) and a LiteLLM gateway adapter.
- Canonical graph-aware receipt schema, deterministic Run Lab fixtures, offline
  evidence import/reconciliation, and experimental single-host envelopes.
- **`forecost compare`** — a narrow matched-cohort economic/outcome prototype.
  Bare comparison of two valid existing run IDs is diagnostic and always abstains. A potentially
  qualifying result requires digest-bound arm manifests, a strict predeclared
  policy, at least 30 matched pairs, final `delta` meters with complete
  one-to-one USD list-rate valuation coverage, predeclared deterministic
  test/build outcome evidence, and deterministic confidence bounds. Results are
  observational, not causal savings or provider-billing claims.
- Three read-only optional MCP tools for canonical run discovery, receipt reads,
  and abstaining two-run comparison diagnostics; the base wheel does not
  advertise an optional-dependency console script. Read-only is a logical
  Forecost-row/schema boundary; SQLite `mode=ro` may create/update WAL/SHM
  coordination sidecars, and `immutable=1` is not used because it can omit
  committed WAL pages.

### Fixed
- **Event double-count**: dedup now keys on the API `requestId`, not per-content-
  block `uuid` — one API response counts once (was up to ~2.25x inflation).
- **Spend double-count**: operational totals now select one canonical posting
  per event instead of summing pricing_table + source_reported valuations.
- **Pricing**: corrected Opus 4.8 ($5/$25), Fable 5 ($10/$50), Haiku 4.5
  ($1/$5) and added current Opus/Sonnet tiers; unknown models are flagged as
  guessed rather than silently priced.
- **Estimator**: shrinkage now blends toward the global pool (was collapsing
  toward zero); estimate↔actual calibration associates by session + time window.
- **Ingest durability**: the byte cursor advances only past newline-terminated,
  successfully-emitted lines; schema-invalid complete records are skipped
  without pinning the cursor; the async flush is a real drain barrier.
- **Recovery durability**: failed batches publish immutable per-batch spools;
  replay preserves the original amount, basis, and pricing provenance and
  cannot overwrite a concurrently spilled batch. Successful replay publishes a
  finite summary before deleting the original queue, so an archive failure
  retains the original for idempotent retry instead of preserving raw source
  fields in the archive.
- **Transaction integrity**: every writer sharing the process connection uses
  one transaction lock; reconciliation is unique and conflict-safe per estimate.
- **Policy**: `scope="run"` is rejected at parse time; a session-scoped rule with
  no active session no longer measures all-time spend.
- **Privacy and deletion**: all persisted event fields are bounded and validated;
  transcript cursors and diagnostic fingerprints are installation-keyed; file
  replacement is detected; privacy verification streams all regular files and
  fails inconclusive on skipped/unreadable paths; custom data roots are never
  claimed or purged without an ownership marker. The legacy `costs.db` contract
  remains deliberately separate and can contain legacy project configuration.
- **Receipt semantics**: trace-scoped span keys prevent cross-trace collisions;
  timing is derived only from explicit interval facts; receipt schema v2 keeps
  competing valuations without summing them; claim profiles expose independent
  completeness, freshness, and contradiction axes.
- **Economic authority**: arbitrary JSON/CSV imports are
  `user_imported_claim`, never self-asserted provider billing. Schema v11
  append-supersedes provenance-proven historical local-import rows without
  rewriting the journal.
- **SQLite durability**: the canonical ledger uses WAL with
  `synchronous=FULL`; schema migration uses a verified SQLite Backup API
  snapshot and validates integrity before and after migration.
- **Comparison evidence validation**: comparisons read one WAL-consistent
  in-memory Backup API copy, verify the journal chain, and deterministically
  rebuild/hash-check journal-derived projections. Broken chain/projection/rebuild
  evidence is invalid; more than 1,000,000 global journal rows abstains; any
  non-journal-derived reconciliation batch abstains. Bootstrap seeds use only a
  fixed protocol label plus sorted quantitative pairs, preventing opaque-label
  seed grinding, and CLI diagnostic IDs are validated before opening the ledger.
- **Plugin supply chain**: Claude lifecycle hooks never install packages. The
  runtime bootstrap is disabled; hooks invoke only the reviewed executable in
  the plugin-owned environment and remain fail-open when it is absent.
- **Packaging**: the optional LiteLLM extra is bounded to the wheel-tested
  compatibility line, avoiding an undeclared modern Rust requirement in CI and
  on macOS/Python 3.12 installs.
- **Product boundary**: removed hidden root aliases for forecast-era commands,
  removed the legacy `init --smart` upload path, and made `ledger.db` versus
  legacy `costs.db` explicit in CLI help and machine-readable capabilities.

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
