# llmlab

**Know what your AI project will cost. Before you build it.**

[![PyPI version](https://img.shields.io/pypi/v/llmlab.svg)](https://pypi.org/project/llmlab/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<!-- GIF placeholder: demo output -->

## The Problem

LLM API costs are unpredictable. You prototype with GPT-4, ship to production, and the first month's bill arrives as a surprise. Most teams have no way to forecast spend until it's too late. llmlab fixes this by learning from your actual usage and giving you accurate cost projections before you scale.

## How It Works

```bash
pip install llmlab
llmlab init
# ... build your project ...
llmlab forecast
```

Initialize at project start, build as usual, and run `forecast` whenever you need a cost estimate. The more you use it, the smarter it gets.

## See It in Action

`llmlab demo` runs a forecast with sample data and no setup. Use it to see the full output before tracking your own project.

## The Magic: It Learns

llmlab improves its predictions as your usage data grows. Early forecasts are rough; later ones converge on reality.

| Day | What happens |
|-----|-------------|
| 0 | Baseline estimate from code analysis |
| 1-3 | Rough forecast, wide prediction intervals |
| 4-7 | Forecast stabilizing, intervals narrowing |
| 8-14 | Reliable forecast, MASE < 1.0 |
| 15+ | High-confidence projection |

## Auto-Tracking (Zero Code Changes)

```python
import llmlab
llmlab.auto_track()
```

Call `auto_track()` once at startup. llmlab intercepts OpenAI, Anthropic, and other provider calls automatically. No decorators, no manual logging.

Note: `auto_track()` captures non-streaming calls automatically. For streaming responses, call `log_stream_usage` after consuming the stream:

```python
llmlab.log_stream_usage(response_data)
```

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
| `llmlab forecast --tui` | Interactive TUI dashboard (requires `pip install llmlab[tui]`) |
| `llmlab forecast --json` | JSON output for CI/scripts |
| `llmlab forecast --exit-code` | Exit 1 if projected over budget, 2 if actual over budget (for CI) |
| `llmlab status` | Show current usage and summary |
| `llmlab track` | View recent tracked LLM calls |
| `llmlab watch` | Live cost dashboard; updates as your app makes calls |
| `llmlab demo` | Run forecast with sample data, no setup needed |
| `llmlab optimize` | Suggest cost optimizations based on usage |
| `llmlab reset` | Reset the current project (optionally keep usage logs) |
| `llmlab serve` | Run local API server for programmatic access |

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

llmlab uses an ensemble of three statistical forecasting methods
(Simple Exponential Smoothing, Damped Trend, and Linear Regression)
inspired by the M4 Forecasting Competition, where simple combinations
beat complex ML models across 100,000 time series.

| Metric | What it means | Typical result |
|--------|--------------|----------------|
| MASE | Are we beating a naive guess? | < 1.0 after 5 days |
| MAE | How many dollars could we be off? | Decreases as data grows |
| 80% interval | Will the real cost land here? | ~80% of the time |
| 95% interval | Conservative budget range | ~95% of the time |

Install the ensemble engine for best results: `pip install llmlab[forecast]`

The base install uses a simpler exponential moving average that works
without additional dependencies.

## Why llmlab?

| Feature | llmlab | LiteLLM | Helicone | LangSmith |
|---------|--------|---------|----------|-----------|
| Cost tracking | Yes | Yes | Yes | Yes |
| Cost forecasting | Yes | No | No | No |
| Prediction intervals | Yes | No | No | No |
| Zero infrastructure | Yes | No (proxy) | No (cloud) | No (cloud) |
| Local-only / private | Yes | Partial | No | No |
| pip install, 2 lines | Yes | SDK wrapper | Proxy setup | SDK setup |
| Free forever | Yes | Freemium | Freemium | $39/seat/mo |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
