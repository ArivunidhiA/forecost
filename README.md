# llmlab

**Know what your AI project will cost. Before you build it.**

[![PyPI version](https://img.shields.io/pypi/v/llmlab.svg)](https://pypi.org/project/llmlab/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/ArivunidhiA/llmlab.svg)](https://github.com/ArivunidhiA/llmlab)

<!-- GIF placeholder -->

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

## The Magic: It Learns

llmlab improves its predictions as your usage data grows. Early forecasts are rough; later ones converge on reality.

| Day  | Forecast (30-day) | Actual Trend | Accuracy |
|------|-------------------|--------------|----------|
| 3    | $120 - $180       | Early ramp   | ~40%     |
| 7    | $95 - $130        | Pattern seen | ~75%     |
| 14   | $102 - $108       | Converging   | ~95%     |

By day 14, the model has enough data to self-correct for pricing changes and usage patterns. You get forecasts you can trust.

## Auto-Tracking (Zero Code Changes)

```python
import llmlab
llmlab.auto_track()
# That's it. Every LLM call is now tracked.
```

Call `auto_track()` once at startup. llmlab intercepts OpenAI, Anthropic, and other provider calls automatically. No decorators, no manual logging.

## Manual Tracking

For fine-grained control, use the `@track_cost` decorator or `log_call`:

```python
import llmlab

@llmlab.track_cost(provider="openai")
def call_gpt(prompt: str):
    return openai.ChatCompletion.create(model="gpt-4", messages=[{"role": "user", "content": prompt}])

# Or log calls manually
llmlab.log_call(model="gpt-4", tokens=150, cost=0.003, provider="openai")
```

## Commands

| Command | Description |
|---------|-------------|
| `llmlab init` | Initialize project and create `.llmlab` config |
| `llmlab forecast` | Show cost forecast in terminal |
| `llmlab forecast --tui` | Interactive TUI dashboard |
| `llmlab forecast --json` | JSON output for CI/scripts |
| `llmlab status` | Show current usage and summary |
| `llmlab track` | Start tracking session |
| `llmlab serve` | Run local API server for dashboards |

## Advanced Usage

- **TUI dashboard**: `pip install llmlab[tui]` then `llmlab forecast --tui`
- **JSON output for CI**: `llmlab forecast --json`
- **Local API server**: `llmlab serve`
- **Smart init with LLM**: `pip install llmlab[llm]` then `llmlab init --smart`

## How Forecasting Works

llmlab uses **Adaptive Exponential Smoothing** on your daily spend. It weights recent days more heavily and adjusts for trends. Pricing ratios (cost per token) are inferred from your data and self-correct when provider prices change. The result is a forecast that adapts to your project's actual usage, not generic benchmarks.

## Contributing

Contributions are welcome. Please open an issue or pull request on [GitHub](https://github.com/ArivunidhiA/llmlab).

## License

MIT
