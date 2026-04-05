# forecost Architecture

**Version:** 0.2.0  
**Purpose:** Local-first LLM cost forecasting that learns from usage patterns

---

## Directory Structure

```
forecost/
├── forecost/                    # Main package (22 modules total)
│   ├── __init__.py              # Public API exports with lazy loading
│   ├── cli.py                   # Click CLI entry point, command registry
│   ├── db.py                    # SQLite persistence, WriteQueue for async batching
│   ├── forecaster.py            # Ensemble forecasting engine (SES + Damped Trend + Linear)
│   ├── interceptor.py           # httpx monkey-patching for auto-tracking
│   ├── pricing.py               # 80+ model pricing database, cost calculation
│   ├── scope.py                 # Heuristic and LLM-powered project scope analyzer
│   ├── tracker.py               # Public tracking API (auto_track, track_cost, log_call)
│   ├── tui.py                   # Textual dashboard with plotext charts
│   └── commands/                # CLI command implementations (13 files)
│       ├── calc_cmd.py          # Cost comparison across models
│       ├── demo_cmd.py          # Demo forecast with synthetic data
│       ├── export_cmd.py        # CSV/JSON export of usage logs
│       ├── forecast_cmd.py      # Main forecast command (rich, markdown, csv, json, tui)
│       ├── init_cmd.py          # Project initialization with scope analysis
│       ├── optimize_cmd.py      # Tier-aware cost optimization suggestions
│       ├── price_cmd.py         # LLM pricing table with filters
│       ├── reset_cmd.py         # Project reset (keep or delete data)
│       ├── serve_cmd.py         # Local HTTP API server (4 endpoints)
│       ├── status_cmd.py        # One-line project status summary
│       ├── track_cmd.py         # View recent tracked calls
│       └── watch_cmd.py         # Live dashboard updating as calls arrive
├── tests/                       # Test suite (94 tests)
│   ├── conftest.py              # pytest fixtures (db_path, cli_runner)
│   ├── test_cli.py              # CLI entry point tests
│   ├── test_commands.py         # Command integration tests (export, serve, calc)
│   ├── test_db.py               # Database schema and WriteQueue tests
│   ├── test_forecaster.py       # Ensemble forecasting, drift detection tests
│   ├── test_interceptor.py      # httpx interception tests
│   ├── test_pricing.py          # Pricing resolution and tier classification
│   ├── test_production.py       # Real-world scenario tests
│   ├── test_sdk_compat.py       # SDK compatibility tests
│   └── test_tracker.py          # Manual tracking API tests
│   └── benchmarks/              # Accuracy benchmarks
├── .github/workflows/           # CI/CD
│   ├── ci.yml                   # Lint, test matrix (3.10-3.12 × ubuntu/mac/win)
│   └── release.yml              # PyPI publish on GitHub release
├── pyproject.toml               # Package metadata, dependencies, entry points
├── README.md                    # User-facing documentation
├── CHANGELOG.md                 # Version history
├── CONTRIBUTING.md              # Development setup, PR process
└── CLAUDE.md                    # Context for AI assistants
```

---

## Module Relationships

```
                        ┌─────────────────┐
                        │   User Code     │
                        └────────┬────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
       ┌────────────┐    ┌──────────────┐    ┌──────────┐
       │auto_track()│    │@track_cost   │    │log_call()│
       │(tracker.py)│    │(tracker.py)  │    │(tracker.py)
       └─────┬──────┘    └──────┬───────┘    └────┬─────┘
              │                  │                  │
              └──────────────────┼──────────────────┘
                                 │
                                 ▼
                    ┌────────────────────┐
                    │  interceptor.py    │
                    │  (httpx patching)  │
                    └─────────┬──────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
       ┌──────────┐    ┌──────────┐    ┌──────────┐
       │ pricing  │    │   db     │    │ tracker  │
       │(calculate│◄───│(WriteQueue│    │(_record_ │
       │  _cost)  │    │  batch)  │    │  usage)  │
       └──────────┘    └────┬─────┘    └──────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ SQLite costs │
                    │     .db      │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │forecast  │ │commands/ │ │tui.py    │
       │(_cmd.py) │ │(cli)     │ │(dashboard│
       │           │ │          │ │  view)   │
       └─────┬─────┘ └──────────┘ └──────────┘
             │
             ▼
       ┌──────────┐
       │forecaster│
       │(ensemble │
       │ engine)  │
       └──────────┘
```

**Key Import Chains:**
- `cli.py` → all `commands/*.py`
- `tracker.py` → `interceptor.py` + `pricing.py` + `db.py`
- `interceptor.py` → `pricing.py` + `db.py`
- `forecaster.py` → `db.py`
- `commands/forecast_cmd.py` → `forecaster.py` + `tui.py`
- `__init__.py` → lazy loads via `__getattr__` to avoid circular imports

---

## Data Flow: A Cost Tracking Call

### Path 1: Auto-Tracking (via httpx interception)

```
1. User calls openai.chat.completions.create()
   └── uses httpx internally

2. interceptor._patched_send() intercepts response
   ├── _extract_model(): parses model from JSON response
   ├── _extract_usage(): extracts prompt/completion tokens
   │   ├── OpenAI format: prompt_tokens + completion_tokens
   │   └── Anthropic format: input_tokens + output_tokens
   ├── pricing.calculate_cost(): converts tokens to USD
   │   └── pricing._resolve_model(): matches model to pricing table
   │       ├── Exact match in FALLBACK_PRICING dict
   │       ├── Date-stripped match (e.g., "gpt-4o-2024-11-20" → "gpt-4o")
   │       └── Prefix match for unknown variants
   └── db.WriteQueue.put(): enqueues for async batch insert

3. WriteQueue._worker() (background thread)
   ├── Batches every 100 items OR 2 seconds (whichever first)
   ├── _insert_usage_logs_batch(): executes SQLite INSERT
   └── On failure: writes to ~/.forecost/recovery.jsonl

4. interceptor._record_usage() updates session stats
   └── tracker._session_stats: in-memory aggregation
```

### Path 2: Manual Tracking (decorator/context manager)

```
1. @track_cost decorator wraps function returning dict with "usage" key
   └── _process_result() extracts tokens, calculates cost

2. log_call() or track() context manager
   └── Direct call to _record_usage() + WriteQueue.put()

3. Both paths converge at db.WriteQueue for persistence
```

### Path 3: Forecast Generation

```
1. forecost forecast command
   └── forecast_cmd._cmd() loads project

2. ProjectForecaster.calculate_forecast()
   ├── db.get_daily_costs(): aggregates by calendar day
   ├── db.get_bucketed_costs(): 15min/5min/1min buckets
   │   └── Adaptive: tries 15min → 5min → 1min until >=3 data points
   ├── Chooses series: buckets if n_buckets > n_days, else daily
   ├── Runs ensemble models:
   │   ├── _ses_forecast(): Simple Exponential Smoothing (n>=2)
   │   ├── _damped_trend_forecast(): ETS damped trend (n>=10)
   │   └── _linear_forecast(): Linear regression (n>=3)
   ├── Equal-weight combination of successful models
   ├── Calculates prediction intervals from SES residuals
   ├── Drift detection: compares recent burn ratios to baseline
   └── db.save_forecast(): persists result

3. Output formatting:
   ├── Rich table (default)
   ├── --output markdown: project summary
   ├── --output csv: key-value pairs
   ├── --output json: full forecast dict
   └── --tui: launches ForecastDashboard
```

---

## Key Design Decisions

### 1. Local-Only Architecture

**Rationale:** Many teams cannot send cost data to cloud services (compliance, IP protection).

**Implementation:**
- SQLite database at `~/.forecost/costs.db` (shared across projects)
- httpx interception happens post-response, zero network overhead
- No outbound API calls except optional LLM scope analysis (user-initiated)

### 2. SQLite with WAL Mode

**Why SQLite:**
- Zero configuration, single file, transactional
- Python standard library (no extra dependency for core)

**Optimizations:**
- `PRAGMA journal_mode=WAL`: read concurrency
- `PRAGMA busy_timeout=5000`: resilience to concurrent writes
- `PRAGMA synchronous=NORMAL`: balance durability/performance

### 3. Async WriteQueue

**Problem:** Synchronous DB writes on every LLM call would block user code.

**Solution:**
- Background thread with `Queue` (maxsize=10,000, drops on overflow)
- Batch: 100 items OR 2 seconds (whichever first)
- Ateexit handler: 1-second timeout for graceful shutdown
- Recovery file: failed batches written to JSONL for manual replay

### 4. Ensemble Forecasting (vs. ML)

**Decision:** Three-model combination (SES + Damped Trend + Linear) rather than neural networks.

**Rationale:**
- M4 Forecasting Competition finding: simple combinations beat complex ML across 100,000 series
- Short LLM usage series (often <30 days) lack data for ML training
- No heavy dependencies (statsmodels optional, ~3MB vs. 500MB+ for torch)
- Interpretable: user can see which models contributed

**Fallback:** Hand-rolled EMA when statsmodels unavailable (`pip install forecost[forecast]`)

### 5. Tier-Based Optimization

**Problem:** Blind "use cheaper model" advice ignores capability requirements.

**Solution:**
- `pricing.MODEL_TIERS`: 3 capability tiers (Heavy/Standard/Economy)
- `optimize` command classifies user's actual usage patterns
- Suggests alternatives only within same tier
- Rationale in output: "Your task uses Tier 1 models (heavy reasoning). Switching to gpt-4o-mini (Tier 3) may reduce quality."

### 6. Dual-Mode Display (Tokens + Dollars)

**Motivation:** Serve both API users (dollar costs) and subscription users (token burn rates).

**Implementation:**
- All CLI commands display both metrics side-by-side
- Token counts from usage_logs table
- Costs from pricing module

---

## Anomaly Detection Algorithm

### Drift Detection (in forecaster.py)

**Purpose:** Alert when spending deviates significantly from baseline.

**Method:**

```python
# Calculate burn ratios for each active day
daily_burn_ratios = [cost / baseline_daily for cost in daily_costs]

# Examine last N days (N = min(5, len(daily_costs)))
last_ratios = daily_burn_ratios[-last_n:]

# Count consecutive days above/below thresholds
consecutive_over = 0
for r in reversed(last_ratios):
    if r > 1.5:  # 50% over baseline
        consecutive_over += 1
    else:
        break

consecutive_under = 0
for r in reversed(last_ratios):
    if r < 0.5:  # 50% under baseline
        consecutive_under += 1
    else:
        break

# Determine status
if smoothed_ratio > 1.5 and consecutive_over >= 3:
    drift_status = "over_budget"
elif smoothed_ratio < 0.5 and consecutive_under >= 3:
    drift_status = "under_budget"
else:
    drift_status = "on_track"
```

**Thresholds:**
- Trigger: 50% deviation (ratio >1.5 or <0.5)
- Persistence: 3+ consecutive days (avoids one-off spikes)
- Uses smoothed_ratio from ensemble forecast, not raw daily costs

### Confidence Scoring

**Based on calendar days of usage (not bucket count):**

| Days | Confidence   | Rationale                          |
|------|--------------|-----------------------------------|
| 0    | low          | No data, baseline only            |
| 1-3  | medium-low   | Single digit days, high variance  |
| 4-7  | medium       | Weekly pattern emerging           |
| 8-14 | high         | Two weeks of history              |
| 15+  | very-high    | Strong statistical foundation     |

### Prediction Intervals

**Method:** Derived from SES residuals using normal approximation.

```python
# Standard deviation of residuals
sigma = sqrt(sum(r**2 for r in residuals) / len(residuals))

# For horizon h days ahead, interval widens with sqrt(h)
daily_forecast = projected_remaining / remaining_days
lower_80 = [max(0, daily_forecast - 1.28 * sigma * sqrt(h+1)) for h in range(remaining_days)]
upper_80 = [daily_forecast + 1.28 * sigma * sqrt(h+1) for h in range(remaining_days)]

# 95% interval uses 1.96 instead of 1.28 (z-scores)
```

**Edge Cases:**
- sigma <= 0: no intervals (perfect fit or single point)
- Bucket mode: sigma scaled by sqrt(buckets_per_day) to get daily-level
- Lower bound clamped to 0 (costs cannot be negative)

### Stability Tracking

**Purpose:** Show if forecast is converging as more data arrives.

```python
history_totals = [h["projected_total"] for h in forecast_history]
history_totals.append(current_projected_total)
recent = history_totals[-5:]  # Last 5 forecasts

changes = [abs(recent[i] - recent[i-1]) / max(recent[i], 0.001) * 100 
           for i in range(1, len(recent))]

avg_change = sum(changes) / len(changes)
stability_label = "converged" if avg_change < 5 else \
                  "stabilizing" if avg_change <= 15 else "adjusting"
```

---

## Public API Surface

### Package-Level Exports (forecost/__init__.py)

**Lazy-loaded via __getattr__ (imports on first use):**

```python
forecost.auto_track()           # Enable httpx interception
forecost.track_cost(provider)   # Decorator for manual tracking
forecost.track()                # Context manager for manual tracking
forecost.log_call(...)          # Direct call logging
forecost.log_stream_usage(...)  # Log consumed streaming response
forecost.get_session_summary()  # In-memory session stats
forecost.get_interceptor_stats() # Interception counters
forecost.disable()              # Uninstall + set FORECOST_DISABLED=1
forecost.__version__            # "0.2.0"
```

### Module-Level Functions

**forecost.tracker:**
```python
def auto_track() -> None
@contextmanager
def track() -> Iterator[Tracker]
class Tracker:
    def log_call(self, model: str, tokens_in: int, tokens_out: int, 
                 provider: str = "openai", metadata: dict | None = None) -> None

def track_cost(provider: str = "openai") -> Callable[[Callable], Callable]
def log_call(model: str, tokens_in: int, tokens_out: int,
             provider: str = "openai", metadata: dict | None = None) -> None
def log_stream_usage(response_data: dict) -> None
def get_session_summary() -> dict
```

**forecost.interceptor:**
```python
def install(on_usage: Callable | None = None) -> None
def uninstall() -> None
def set_project_id(project_id: int | None) -> None
def set_on_usage(callback: Callable | None) -> None
def log_stream_usage(response_data: dict) -> None
def get_interceptor_stats() -> dict
```

**forecost.pricing:**
```python
def calculate_cost(model: str, tokens_in: int, tokens_out: int) -> float
def get_provider(model: str) -> str
def get_tier(model: str) -> str
FALLBACK_PRICING: dict[str, dict[str, float]]  # 80+ models
DEFAULT_COST: dict[str, float]  # {"input": 5.0, "output": 15.0}
MODEL_TIERS: dict[str, list[str]]  # 3 capability tiers
```

**forecost.db:**
```python
def get_or_create_db() -> sqlite3.Connection
def create_project(name: str, path: str, baseline_daily_cost: float,
                   baseline_total_days: int, baseline_total_cost: float,
                   metadata: dict | None = None) -> int
def get_project_by_path(path: str) -> dict | None
def get_daily_costs(project_id: int) -> list[tuple[str, float, int]]  # (day, cost, tokens)
def get_bucketed_costs(project_id: int, bucket_minutes: int = 15) -> list[tuple[str, float, int]]
def get_recent_usage_logs(project_id: int, limit: int = 20) -> list[dict]
def get_forecast_history(project_id: int) -> list[dict]
def save_forecast(project_id: int, iteration: int, projected_total: float, ...) -> int

class WriteQueue:
    def put(self, project_id: int, timestamp: str, model: str, provider: str,
            tokens_in: int, tokens_out: int, cost_usd: float,
            metadata: str | None = None, source: str = "api") -> None
```

**forecost.forecaster:**
```python
class ProjectForecaster:
    def __init__(self, project_id: int) -> None
    def calculate_forecast(self, *, save: bool = False) -> dict
    # Returns dict with 20+ fields including:
    # - project_id, project_name, actual_spend, projected_total, projected_remaining
    # - remaining_days, active_days, confidence, drift_status
    # - prediction_interval_80, prediction_interval_95, mase, mae_dollars
    # - model_breakdown, models_used, n_models_used, stability_label
```

**forecost.scope:**
```python
def analyze_heuristic(project_path: str) -> dict
    # Returns: estimated_days, daily_cost, total_cost, confidence, source,
    #          project_type, model, calls_per_day, tokens_in, tokens_out

def analyze_with_llm(project_path: str, api_key: str | None = None) -> dict
    # Same format, falls back to heuristic if litellm unavailable
```

**forecost.tui:**
```python
def launch(forecast_result: dict, project_id: int, on_refresh: Callable | None = None) -> None
    # Launches ForecastDashboard Textual app
```

### CLI Entry Points (forecost.cli:main)

```bash
forecost calc "prompt" [--file FILE] [--models MODELS] [--json]
forecost price [--tier 1|2|3] [--json]
forecost init [--budget USD] [--force]
forecost forecast [--output FORMAT] [--tui] [--json] [--brief] [--exit-code]
forecost status
forecost track [--limit N]
forecost watch [--refresh SECONDS]
forecost optimize [--savings-target PERCENT]
forecost export [--format csv|json]
forecost reset [--keep-data] [--yes]
forecost serve [--port PORT] [--host HOST]
forecost demo
```

### Configuration File (.forecost.toml)

```toml
name = "my-project"
path = "."
baseline_daily_cost = 5.0
baseline_total_days = 14
baseline_total_cost = 70.0
created_at = "2026-03-10T12:00:00Z"
budget = 100.0  # Optional USD cap
```

---

## Schema

**projects table:**
```sql
id INTEGER PRIMARY KEY
name TEXT NOT NULL
path TEXT NOT NULL UNIQUE
baseline_daily_cost REAL NOT NULL
baseline_total_days INTEGER NOT NULL
baseline_total_cost REAL NOT NULL
metadata TEXT  -- JSON
created_at TEXT NOT NULL  -- ISO8601
```

**usage_logs table:**
```sql
id INTEGER PRIMARY KEY
project_id INTEGER REFERENCES projects(id)
timestamp TEXT NOT NULL  -- ISO8601
model TEXT NOT NULL
provider TEXT NOT NULL
tokens_in INTEGER NOT NULL
tokens_out INTEGER NOT NULL
cost_usd REAL NOT NULL
metadata TEXT  -- JSON
source TEXT DEFAULT 'api'  -- api, cursor, claude
```

**forecasts table:**
```sql
id INTEGER PRIMARY KEY
project_id INTEGER REFERENCES projects(id)
iteration INTEGER NOT NULL
projected_total REAL NOT NULL
projected_remaining_days INTEGER NOT NULL
smoothed_burn_ratio REAL NOT NULL
confidence TEXT NOT NULL
active_days_count INTEGER NOT NULL
mape REAL
created_at TEXT NOT NULL
```

---

## Error Handling Philosophy

**Never fail the user's code because of cost tracking:**
- All interceptor errors caught and logged to `~/.forecost/error.log`
- WriteQueue drops items on full queue (never blocks)
- Recovery file for database write failures
- Graceful degradation: missing pricing → DEFAULT_COST, missing statsmodels → EMA fallback
