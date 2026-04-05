# Test Files Documentation

## test_forecaster.py - Ensemble Forecasting Tests

Comprehensive tests for the ensemble forecasting engine.

### Key Test Fixtures

```python
@pytest.fixture
def synthetic_project(tmp_path, monkeypatch):
    """Creates a project with 14 days of synthetic usage data."""
    db_path = tmp_path / "costs.db"
    monkeypatch.setattr("forecost.db._DB_PATH", db_path)
    monkeypatch.setattr("forecost.db._conn", None)
    pid = create_project(
        name="fc",
        path=str(tmp_path),
        baseline_daily_cost=10.0,
        baseline_total_days=14,
        baseline_total_cost=140.0,
    )
    # Insert 14 days of $10/day usage
    items = [
        (pid, (base - timedelta(days=13 - i)).isoformat(), "gpt-4o-mini", "openai", 1000, 500, 10.0, None)
        for i in range(14)
    ]
    _insert_usage_logs_batch(conn, items)
    return pid
```

### Test Categories

**Basic Functionality:**
- `test_project_forecaster_with_synthetic_data()` - End-to-end forecast validation
- `test_forecast_includes_total_tokens()` - Token tracking verification

**Confidence Scoring:**
- `test_confidence_scoring_at_different_day_counts()` - Validates confidence thresholds:
  - 0 days → "low"
  - 2 days → "medium-low"
  - 5 days → "medium"
  - 10 days → "high"

**Drift Detection:**
- `test_drift_detection_over_budget()` - Tests consecutive burn ratio >1.5 for 3+ days triggers "over_budget"

**Ensemble Behavior:**
- `test_ensemble_uses_ses_only_with_few_points()` - With 5 points: only SES (n>=2), no damped_trend (requires 10)
- `test_ensemble_uses_all_three_models()` - With 14 points: all three models active
- `test_fallback_when_statsmodels_unavailable()` - EMA fallback works without numpy/statsmodels

**Statistical Validation:**
- `test_prediction_intervals_widen_with_horizon()` - 95% interval wider than 80%
- `test_mase_below_one_for_stable_data()` - MASE < 1.0 means beating naive forecast

**Bucketed Data:**
- `test_bucketed_costs_returns_15min_intervals()` - SQL time bucketing correct
- `test_forecaster_prefers_buckets_over_daily()` - Intra-day data triggers bucket mode
- `test_adaptive_buckets_avoids_ema_fallback()` - Fine-grained buckets enable ensemble
- `test_day_one_accuracy_with_buckets()` - Day 1 with 8 calls → ensemble activates

---

## test_tracker.py - Manual Tracking API Tests

Tests for the public tracking API.

### Session Management Pattern

```python
@pytest.fixture(autouse=True)
def reset_session():
    """Reset global session stats before/after each test."""
    import forecost.tracker as mod
    mod._session_stats = {}
    yield
    mod._session_stats = {}
```

### Test Cases

**Session Aggregation:**
- `test_log_call_adds_to_session()` - Multiple calls aggregate correctly
- `test_get_session_summary_returns_correct_totals()` - Token counts and costs accurate

**Decorator Patterns:**
- `test_track_cost_decorator_sync()` - Sync function wrapping
- `test_track_cost_decorator_async()` - Async function wrapping with `asyncio.run()`

**Context Manager:**
- `test_track_context_manager()` - `with track() as t:` pattern works

**Edge Cases:**
- `test_auto_track_no_project_does_not_install()` - No .forecost.toml → warning printed, no crash

### Key Patterns Demonstrated

1. **Monkeypatching for isolation:**
   ```python
   monkeypatch.setattr("forecost.tracker._find_project", lambda: None)
   ```

2. **Expected cost calculation:**
   ```python
   expected_cost = (1_000_000 / 1_000_000) * 0.15 + (500_000 / 1_000_000) * 0.60
   ```

3. **Async testing:**
   ```python
   result = asyncio.run(fake_async_call())
   ```

---

## test_commands.py - CLI Integration Tests

End-to-end tests using Click's CliRunner.

### Fixture Pattern

```python
@pytest.fixture
def cli_runner():
    return CliRunner()

def _init_project(cli_runner, tmp_path, db_path, monkeypatch):
    """Helper: init project with required files."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("import openai\n")
    (tmp_path / "README.md").write_text("chatbot\n")
    monkeypatch.setattr("forecost.db._DB_PATH", db_path)
    monkeypatch.setattr("forecost.db._conn", None)
    result = cli_runner.invoke(main, ["init"])
    assert result.exit_code == 0
    return result
```

### Export Tests

- `test_export_csv()` - CSV output format validation
- `test_export_json()` - JSON output parseable

### Output Format Tests

- `test_forecast_output_markdown()` - Markdown tables rendered
- `test_forecast_output_csv()` - CSV key-value pairs
- `test_forecast_exit_code_on_budget()` - Exit 0 when under budget
- `test_forecast_exit_code_over_budget()` - Exit 2 when actual > budget

### Reset Tests

- `test_reset_keep_data()` - `--keep-data` preserves usage_logs, removes project
- `test_reset_full()` - Full reset clears all tables

### Server Test

- `test_serve_health()` - HTTP server responds to `/api/health`
  - Uses `HTTPServer` in thread
  - `urllib.request` for verification
  - Proper shutdown with `server.shutdown()`

### Streaming Tests

- `test_log_stream_usage_openai_format()` - `prompt_tokens`/`completion_tokens` parsing
- `test_log_stream_usage_anthropic_format()` - `input_tokens`/`output_tokens` parsing
  - Both use `time.sleep(2.5)` to wait for WriteQueue flush

### Calc/Price Command Tests

- `test_calc_command_basic()` - Rich table output
- `test_calc_command_json()` - JSON parseable with expected keys
- `test_calc_no_prompt_fails()` - Exit code non-zero on missing arg
- `test_price_command_table()` - Pricing table rendered
- `test_price_command_json()` - JSON array of models
- `test_price_filter_tier()` - `--tier 1` filters correctly

---

## Testing Patterns Summary

| Pattern | Usage |
|---------|-------|
| `tmp_path` | Isolated temp directory per test |
| `monkeypatch` | Replace module attributes for isolation |
| `CliRunner` | Invoke Click commands programmatically |
| `time.sleep(2.5)` | Wait for async WriteQueue flush |
| `reset_session` fixture | Clean global state between tests |
| `monkeypatch.chdir()` | Simulate running from project directory |

---

## Test Configuration (conftest.py)

```python
import pytest

@pytest.fixture
def db_path(tmp_path):
    """Provide isolated database path."""
    return tmp_path / "costs.db"

@pytest.fixture
def cli_runner():
    """Provide Click test runner."""
    return CliRunner()
```

Fixtures defined in `conftest.py` are auto-available to all tests in the directory.
