# forecost README

**The Swiss army knife for LLM costs. Local-first, zero infra.**

[![PyPI version](https://img.shields.io/pypi/v/forecost.svg)](https://pypi.org/project/forecost/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python 3.10+ required. forecost is in Alpha: APIs may change and some features are experimental.

---

## Instant Value — No Setup Required

### Compare costs across models instantly

```bash
$ forecost calc "Explain quantum computing in simple terms"

┌─────────────────────────────────────────────────────────────┐
│                     Cost Comparison                         │
├──────────────────────────┬──────────┬──────────┬────────────┤
│ Model                    │ Tier     │ Tokens   │ Cost/call  │
├──────────────────────────┼──────────┼──────────┼────────────┤
│ gpt-4o                   │ Tier 1   │ 8 / 500  │ $0.005020  │
│ gpt-4o-mini              │ Tier 2   │ 8 / 500  │ $0.000301  │
│ claude-3-5-sonnet-latest │ Tier 1   │ 8 / 500  │ $0.007524  │
│ claude-3-5-haiku-latest  │ Tier 2   │ 8 / 500  │ $0.002006  │
│ gemini-2.5-pro           │ Tier 1   │ 8 / 500  │ $0.005010  │
│ gemini-2.5-flash         │ Tier 2   │ 8 / 500  │ $0.000301  │
└──────────────────────────┴──────────┴──────────┴────────────┘
```

### Browse all LLM pricing

```bash
forecost price               # Rich table of all 80+ models
forecost price --json        # Programmatic JSON output
forecost price --tier 1      # Filter by capability tier
```

---

## Quick Start

Full walkthrough from install to forecast:

```bash
pip install forecost
cd your-project
forecost init
```

Add to your app's entry point (before any LLM calls):

```python
import forecost
forecost.auto_track()
```

Call `auto_track()` early, before any httpx usage. If your app imports httpx before forecost, the interceptor may not attach correctly.

Run your app as usual. After building usage for a few days:

```bash
forecost forecast
```

---

## See It in Action

`forecost demo` runs a forecast with sample data and no setup. Use it to see the full output before tracking your own project.

---

## Dual-Mode Tracking: Tokens + Dollars

forecost v0.2.0 tracks both **token burn** and **dollar cost** side by side:

- **API users** see dollar projections and cost optimization suggestions
- **Subscription users** (Cursor, Claude Code) see token burn rates and remaining capacity
- All CLI commands (`status`, `forecast`, `optimize`) display both metrics

---

## Auto-Tracking

Non-streaming calls are tracked automatically. No decorators, no manual logging.

**Streaming limitation:** forecost cannot intercept streaming responses automatically. You must call `log_stream_usage` after consuming the stream. Pass the accumulated response dict containing a `usage` key (and optionally `model` for identification):

```python
import forecost
forecost.auto_track()

# Example: OpenAI streaming
response = client.chat.completions.create(model="gpt-4", messages=[...], stream=True)
accumulated = {"usage": {"prompt_tokens": 0, "completion_tokens": 0}, "model": "gpt-4"}
for chunk in response:
    if chunk.usage:
        accumulated["usage"] = {"prompt_tokens": chunk.usage.prompt_tokens,
                               "completion_tokens": chunk.usage.completion_tokens}
    if chunk.model:
        accumulated["model"] = chunk.model
forecost.log_stream_usage(accumulated)
```

For Anthropic, use `input_tokens` and `output_tokens` instead of `prompt_tokens` and `completion_tokens`.

---

## Manual Tracking

For fine-grained control, use the `@track_cost` decorator or `log_call`:

```python
import forecost

@forecost.track_cost(provider="openai")
def call_gpt(prompt: str):
    return openai.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])

# Or log calls manually
forecost.log_call(model="gpt-4", tokens_in=500, tokens_out=200, provider="openai")
```

---

## Commands

| Command | Description |
|---------|-------------|
| `forecost calc "prompt"` | Instant cost comparison across models |
| `forecost calc --file prompt.txt` | Cost estimate from a file |
| `forecost price` | Browse LLM pricing for all 80+ models |
| `forecost price --json` | Programmatic pricing data |
| `forecost init` | Initialize project and create `.forecost.toml` config |
| `forecost init --budget X` | Set a budget cap in USD |
| `forecost forecast` | Show cost forecast in terminal |
| `forecost forecast --output markdown` | Output forecast as Markdown |
| `forecost forecast --output csv` | Output forecast as CSV |
| `forecost forecast --tui` | Interactive TUI dashboard (requires `pip install forecost[tui]`) |
| `forecost forecast --json` | JSON output for CI/scripts |
| `forecost forecast --brief` | One-line summary (same format as `status`) |
| `forecost forecast --exit-code` | Exit 1 if projected over budget, 2 if actual over budget (for CI) |
| `forecost status` | One-line summary: tokens, spend, projected total, drift status |
| `forecost track` | View recent tracked LLM calls |
| `forecost watch` | Live cost dashboard; updates as your app makes calls |
| `forecost export --format csv` | Export usage data as CSV |
| `forecost export --format json` | Export usage data as JSON |
| `forecost demo` | Run forecast with sample data, no setup needed |
| `forecost optimize` | Tier-aware cost optimization suggestions |
| `forecost reset` | Reset the current project (optionally keep usage logs) |
| `forecost serve` | Run local API server for programmatic access |

`status` and `forecast --brief` both show the same one-line summary. Use `status` when you only need a quick check; use `forecast --brief` when you want that format in a script or CI pipeline.

---

## Budget Enforcement

Set a budget at init with `--budget`:

```bash
forecost init --budget 100
```

Use `--exit-code` on forecast to fail CI when over budget:

```yaml
- name: Check LLM Budget
  run: |
    pip install forecost
    forecost forecast --exit-code
```

Exit codes: 0 = on track, 1 = projected over budget, 2 = actual spend over budget.

---

## Disabling in Tests

```bash
FORECOST_DISABLED=1 pytest
```

Or in code:

```python
forecost.disable()
```

---

## Forecasting Accuracy

forecost uses an ensemble of three statistical forecasting methods (Simple Exponential Smoothing, Damped Trend, and Linear Regression) inspired by the M4 Forecasting Competition, where simple combinations beat complex ML models across 100,000 time series.

| Metric | What it means | Typical result |
|--------|---------------|----------------|
| MASE | Are we beating a naive guess? | < 1.0 after 5 days |
| MAE | How many dollars could we be off? | Decreases as data grows |
| 80% interval | Will the real cost land here? | ~80% of the time |
| 95% interval | Conservative budget range | ~95% of the time |

Install the ensemble engine for best results: `pip install forecost[forecast]`

The base install uses a simpler exponential moving average that works without additional dependencies.

---

## Why forecost?

| Feature | forecost | LiteLLM | Helicone | LangSmith |
|---------|--------|---------|----------|-----------|
| Cost tracking | Yes | Yes | Yes | Yes |
| Cost forecasting | Yes | No | No | No |
| Instant cost calc | Yes | No | No | No |
| LLM pricing database | Yes | Partial | No | No |
| Prediction intervals | Yes | No | No | No |
| Zero infrastructure | Yes | No (proxy) | No (cloud) | No (cloud) |
| Zero overhead on requests | Yes (post-response) | No (proxy latency) | No (proxy latency) | No (SDK wrapper) |
| Local-only / private | Yes | Partial | No | No |
| pip install, 2 lines | Yes | SDK wrapper | Proxy setup | SDK setup |
| Free forever | Yes | Freemium | Freemium | $39/seat/mo |

Minimal footprint: 3 runtime dependencies (click, rich, httpx; plus tomli on Python 3.10), under 3MB.

---

## Data Storage

- **Usage and forecasts:** `~/.forecost/costs.db` (SQLite). All projects share this database.
- **Project config:** `.forecost.toml` in your project root. Contains project name, baseline days, and optional budget.

---

## Glossary

| Term | Meaning |
|------|---------|
| **Confidence levels** | How reliable the forecast is based on data volume: low (0 days), medium-low (1-3), medium (4-7), high (8-14), very-high (15+). More usage data yields higher confidence. |
| **Drift status** | Whether spend is trending above or below the baseline: `on_track`, `over_budget`, or `under_budget`. Based on recent daily burn ratios. |
| **MASE** | Mean Absolute Scaled Error. Compares forecast accuracy to a naive "yesterday = tomorrow" guess. MASE < 1.0 means the forecast beats the naive baseline. |
| **Stability** | How much the forecast changes between runs: `converged` (< 5% change), `stabilizing` (5-15%), or `adjusting` (> 15%). |
| **Prediction intervals** | 80% and 95% ranges around the projected total. The real cost will fall within the 80% interval about 80% of the time. |
| **Model Tiers** | Capability classification: Tier 1 (Heavy) for complex tasks, Tier 2 (Standard) for routine work, Tier 3 (Economy) for simple tasks. Used by `optimize` for intelligent suggestions. |

---

## Local API Server

`forecost serve` starts a local HTTP server (default port 8787) for programmatic access:

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check. Returns `{"status": "ok"}`. |
| `GET /api/forecast` | Full forecast result (same as `forecost forecast --json`). |
| `GET /api/status` | Project status: active days, actual spend, baseline info. |
| `GET /api/costs` | Recent usage logs. |

Run from your project directory so forecost can find `.forecost.toml`.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT
