# llmlab

**Know what your AI project will cost. Before you build it.**

[![PyPI version](https://img.shields.io/pypi/v/llmlab.svg)](https://pypi.org/project/llmlab/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python 3.10+ required. llmlab is in Alpha: APIs may change and some features are experimental.

See `llmlab demo` for a live preview.

## The Problem

LLM API costs are unpredictable. You prototype with GPT-4, ship to production, and the first month's bill arrives as a surprise. Most teams have no way to forecast spend until it's too late. llmlab fixes this by learning from your actual usage and giving you accurate cost projections before you scale.

## Quick Start

Full walkthrough from install to forecast:

```bash
pip install llmlab
cd your-project
llmlab init
```

Add to your app's entry point (before any LLM calls):

```python
import llmlab
llmlab.auto_track()
```

Call `auto_track()` early, before any httpx usage. If your app imports httpx before llmlab, the interceptor may not attach correctly.

Run your app as usual. After building usage for a few days:

```bash
llmlab forecast
```

## See It in Action

`llmlab demo` runs a forecast with sample data and no setup. Use it to see the full output before tracking your own project.

## Auto-Tracking

Non-streaming calls are tracked automatically. No decorators, no manual logging.

**Streaming limitation:** llmlab cannot intercept streaming responses automatically. You must call `log_stream_usage` after consuming the stream. Pass the accumulated response dict containing a `usage` key (and optionally `model` for identification):

```python
import llmlab
llmlab.auto_track()

# Example: OpenAI streaming
response = client.chat.completions.create(model="gpt-4", messages=[...], stream=True)
accumulated = {"usage": {"prompt_tokens": 0, "completion_tokens": 0}, "model": "gpt-4"}
for chunk in response:
    if chunk.usage:
        accumulated["usage"] = {"prompt_tokens": chunk.usage.prompt_tokens,
                               "completion_tokens": chunk.usage.completion_tokens}
    if chunk.model:
        accumulated["model"] = chunk.model
llmlab.log_stream_usage(accumulated)
```

For Anthropic, use `input_tokens` and `output_tokens` instead of `prompt_tokens` and `completion_tokens`.

## Manual Tracking

For fine-grained control, use the `@track_cost` decorator or `log_call`:

```python
import llmlab

@llmlab.track_cost(provider="openai")
def call_gpt(prompt: str):
    return openai.chat.completions.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])

# Or log calls manually
llmlab.log_call(model="gpt-4", tokens_in=500, tokens_out=200, provider="openai")
```

## Commands

| Command | Description |
|---------|-------------|
| `llmlab init` | Initialize project and create `.llmlab.toml` config |
| `llmlab init --budget X` | Set a budget cap in USD |
| `llmlab forecast` | Show cost forecast in terminal |
| `llmlab forecast --output markdown` | Output forecast as Markdown |
| `llmlab forecast --output csv` | Output forecast as CSV |
| `llmlab forecast --tui` | Interactive TUI dashboard (requires `pip install llmlab[tui]`) |
| `llmlab forecast --json` | JSON output for CI/scripts |
| `llmlab forecast --brief` | One-line summary (same format as `status`) |
| `llmlab forecast --exit-code` | Exit 1 if projected over budget, 2 if actual over budget (for CI) |
| `llmlab status` | One-line summary: spend, projected total, day count, drift status |
| `llmlab track` | View recent tracked LLM calls |
| `llmlab watch` | Live cost dashboard; updates as your app makes calls |
| `llmlab export --format csv` | Export usage data as CSV |
| `llmlab export --format json` | Export usage data as JSON |
| `llmlab demo` | Run forecast with sample data, no setup needed |
| `llmlab optimize` | Suggest cost optimizations based on usage |
| `llmlab reset` | Reset the current project (optionally keep usage logs) |
| `llmlab serve` | Run local API server for programmatic access |

`status` and `forecast --brief` both show the same one-line summary. Use `status` when you only need a quick check; use `forecast --brief` when you want that format in a script or CI pipeline.

## Budget Enforcement

Set a budget at init with `--budget`:

```bash
llmlab init --budget 100
```

Use `--exit-code` on forecast to fail CI when over budget:

```yaml
- name: Check LLM Budget
  run: |
    pip install llmlab
    llmlab forecast --exit-code
```

Exit codes: 0 = on track, 1 = projected over budget, 2 = actual spend over budget.

## Disabling in Tests

```bash
LLMLAB_DISABLED=1 pytest
```

Or in code:

```python
llmlab.disable()
```

## Forecasting Accuracy

llmlab uses an ensemble of three statistical forecasting methods (Simple Exponential Smoothing, Damped Trend, and Linear Regression) inspired by the M4 Forecasting Competition, where simple combinations beat complex ML models across 100,000 time series.

| Metric | What it means | Typical result |
|--------|---------------|----------------|
| MASE | Are we beating a naive guess? | < 1.0 after 5 days |
| MAE | How many dollars could we be off? | Decreases as data grows |
| 80% interval | Will the real cost land here? | ~80% of the time |
| 95% interval | Conservative budget range | ~95% of the time |

Install the ensemble engine for best results: `pip install llmlab[forecast]`

The base install uses a simpler exponential moving average that works without additional dependencies.

## Why llmlab?

| Feature | llmlab | LiteLLM | Helicone | LangSmith |
|---------|--------|---------|----------|-----------|
| Cost tracking | Yes | Yes | Yes | Yes |
| Cost forecasting | Yes | No | No | No |
| Prediction intervals | Yes | No | No | No |
| Zero infrastructure | Yes | No (proxy) | No (cloud) | No (cloud) |
| Zero overhead on requests | Yes (post-response) | No (proxy latency) | No (proxy latency) | No (SDK wrapper) |
| Local-only / private | Yes | Partial | No | No |
| pip install, 2 lines | Yes | SDK wrapper | Proxy setup | SDK setup |
| Free forever | Yes | Freemium | Freemium | $39/seat/mo |

Minimal footprint: 3 runtime dependencies (click, rich, httpx), under 3MB.

## Data Storage

- **Usage and forecasts:** `~/.llmlab/costs.db` (SQLite). All projects share this database.
- **Project config:** `.llmlab.toml` in your project root. Contains project name, baseline days, and optional budget.

## Glossary

| Term | Meaning |
|------|---------|
| **Confidence levels** | How reliable the forecast is based on data volume: low (0 days), medium-low (1-3), medium (4-7), high (8-14), very-high (15+). More usage data yields higher confidence. |
| **Drift status** | Whether spend is trending above or below the baseline: `on_track`, `over_budget`, or `under_budget`. Based on recent daily burn ratios. |
| **MASE** | Mean Absolute Scaled Error. Compares forecast accuracy to a naive "yesterday = tomorrow" guess. MASE < 1.0 means the forecast beats the naive baseline. |
| **Stability** | How much the forecast changes between runs: `converged` (< 5% change), `stabilizing` (5-15%), or `adjusting` (> 15%). |
| **Prediction intervals** | 80% and 95% ranges around the projected total. The real cost will fall within the 80% interval about 80% of the time. |

## Local API Server

`llmlab serve` starts a local HTTP server (default port 8787) for programmatic access:

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check. Returns `{"status": "ok"}`. |
| `GET /api/forecast` | Full forecast result (same as `llmlab forecast --json`). |
| `GET /api/status` | Project status: active days, actual spend, baseline info. |
| `GET /api/costs` | Recent usage logs. |

Run from your project directory so llmlab can find `.llmlab.toml`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
