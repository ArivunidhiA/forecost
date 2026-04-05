# forecost

**Know what your LLMs cost. No cloud. No signup. Just `pip install forecost`.**

[![PyPI version](https://img.shields.io/pypi/v/forecost)](https://pypi.org/project/forecost/)
[![Downloads](https://img.shields.io/pypi/dm/forecost)](https://pypi.org/project/forecost/)
[![License: MIT](https://img.shields.io/github/license/ArivunidhiA/forecost)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/ArivunidhiA/forecost/ci.yml)](https://github.com/ArivunidhiA/forecost/actions)
[![Python](https://img.shields.io/pypi/pyversions/forecost)](https://pypi.org/project/forecost/)

<!-- TODO: Replace with demo GIF showing: forecost calc → forecost forecast → TUI dashboard -->
<p align="center">
  <img src="https://via.placeholder.com/800x400?text=Demo+GIF+Coming+Soon" alt="forecost demo" width="800">
</p>

## The Problem

Most developers have no idea what their LLM API calls actually cost until the bill arrives, and by then the damage is done. One team burned $47,000 in 11 days when LangChain agents got stuck in a loop, and 96% of enterprises report AI costs exceeding initial estimates. forecost fixes that by making spend visible and predictable from day one.

## Quickstart

```bash
pip install forecost
```

```python
import forecost
forecost.auto_track()   # Add this before your LLM calls
```

```bash
forecost forecast       # See where your money is going
```

> 💡 No API keys yet? Run `forecost demo` to see a forecast with sample data.

## Compare costs across models instantly

```bash
forecost calc "Explain quantum computing in simple terms"
```

```text
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

Browse all built-in pricing with:

```bash
forecost price
forecost price --json
```

## Why forecost?

| Feature | forecost | LiteLLM | Helicone | LangSmith |
|---------|----------|---------|----------|-----------|
| Cost tracking | ✅ | ✅ | ✅ | ✅ |
| Cost forecasting | ✅ | ❌ | ❌ | ❌ |
| Instant cost calc | ✅ | ❌ | ❌ | ❌ |
| Prediction intervals | ✅ | ❌ | ❌ | ❌ |
| Zero infrastructure | ✅ | ❌ (proxy) | ❌ (cloud) | ❌ (cloud) |
| Local-only / private | ✅ | Partial | ❌ | ❌ |
| pip install + 2 lines | ✅ | ❌ | ❌ | ❌ |
| Free forever | ✅ | Freemium | Freemium | $39/seat/mo |

## Feature Highlights

- Tracks non-streaming LLM calls automatically — zero decorators needed.
- Reports both token burn and dollar cost side by side in every command.
- Forecasts spend using 3 statistical models that beat naive baselines on real cost data.
- Enforces budgets in CI with exit codes — over-budget runs fail fast.
- Includes an 80+ model pricing database for instant cross-provider comparison.
- Offers an optional TUI dashboard with `pip install forecost[tui]`.

## Detailed Usage

### Auto-Tracking

Non-streaming calls are tracked automatically; call `forecost.auto_track()` as early as possible in your entry point.

If your app imports `httpx` before `forecost.auto_track()`, the interceptor may not attach correctly.

Streaming responses are not intercepted automatically, so call `log_stream_usage` after consuming the stream and pass the accumulated response dictionary.

```python
import forecost
forecost.auto_track()

# Example: OpenAI streaming
response = client.chat.completions.create(model="gpt-4", messages=[...], stream=True)
accumulated = {"usage": {"prompt_tokens": 0, "completion_tokens": 0}, "model": "gpt-4"}
for chunk in response:
    if chunk.usage:
        accumulated["usage"] = {
            "prompt_tokens": chunk.usage.prompt_tokens,
            "completion_tokens": chunk.usage.completion_tokens,
        }
    if chunk.model:
        accumulated["model"] = chunk.model

forecost.log_stream_usage(accumulated)
```

For Anthropic, use `input_tokens` and `output_tokens` instead of `prompt_tokens` and `completion_tokens`.

### Manual Tracking

Use the `@track_cost` decorator or `log_call` when you want explicit control:

```python
import forecost

@forecost.track_cost(provider="openai")
def call_gpt(prompt: str):
    return openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
    )
```

```python
import forecost

forecost.log_call(model="gpt-4", tokens_in=500, tokens_out=200, provider="openai")
```

### Budget Enforcement

Set a project budget during initialization:

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

Exit codes: `0` = on track, `1` = projected over budget, `2` = actual spend over budget.

### Disabling in Tests

If you have forecost installed, it automatically disables itself during `pytest` runs via the built-in pytest plugin.

```bash
FORECOST_DISABLED=1 pytest
```

Or disable explicitly in code:

```python
forecost.disable()
```

## Commands Reference

<details>
<summary>📖 Full Command Reference</summary>

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

`status` and `forecast --brief` show the same one-line summary; use `status` for quick checks and `forecast --brief` for scripts/CI.

</details>

## Forecasting Methodology

forecost uses an ensemble of three statistical forecasting methods (Simple Exponential Smoothing, Damped Trend, and Linear Regression) inspired by the M4 Forecasting Competition, where simple model combinations beat many complex ML approaches across large time-series benchmarks.

| Metric | What it means | Typical result |
|--------|---------------|----------------|
| MASE | Are we beating a naive guess? | < 1.0 after 5 days |
| MAE | How many dollars could we be off? | Decreases as data grows |
| 80% interval | Will the real cost land here? | ~80% of the time |
| 95% interval | Conservative budget range | ~95% of the time |

For best results, install the ensemble engine with `pip install forecost[forecast]`; the base install falls back to a lighter exponential moving average.

## Support

If forecost saves you from a surprise LLM bill, consider giving it a ⭐ — it helps other developers find this tool.

## Data Storage

- **Usage and forecasts:** `~/.forecost/costs.db` (SQLite). All projects share this database.
- **Project config:** `.forecost.toml` in your project root. Contains project name, baseline days, and optional budget.

## Local API Server

<details>
<summary>Local API Server (`forecost serve`)</summary>

`forecost serve` starts a local HTTP server (default port `8787`) for programmatic access:

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check. Returns `{"status": "ok"}`. |
| `GET /api/forecast` | Full forecast result (same as `forecost forecast --json`). |
| `GET /api/status` | Project status: active days, actual spend, baseline info. |
| `GET /api/costs` | Recent usage logs. |

Run from your project directory so forecost can find `.forecost.toml`.

</details>

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
