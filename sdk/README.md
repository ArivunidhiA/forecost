# LLMLab SDK

One-line LLM cost tracking, caching, and analytics for OpenAI, Anthropic, and Google.

## Installation

```bash
pip install llmlab
```

With provider extras:

```bash
pip install llmlab[openai]       # OpenAI support
pip install llmlab[anthropic]    # Anthropic support
pip install llmlab[google]       # Google Gemini support
pip install llmlab[all]          # All providers
```

## Quick Start

```python
import openai
from llmlab import patch

# One line to enable tracking — all calls now go through LLMLab proxy
patch(openai, proxy_key="llmlab_pk_your_key_here")

# Use OpenAI as normal — costs are tracked automatically
client = openai.OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

## Supported Providers

| Provider | Module | Status |
| -------- | ------ | ------ |
| OpenAI | `openai` | Fully supported (sync + async) |
| Anthropic | `anthropic` | Fully supported (sync + async) |
| Google Gemini | `google.generativeai` | Supported |

## How It Works

`patch()` monkey-patches the LLM client library to route requests through
the LLMLab proxy. The proxy:

1. Forwards your request to the real provider API
2. Logs token usage, latency, and cost
3. Caches identical requests to save money
4. Checks budget alerts and fires webhooks
5. Returns the response unchanged

Your code stays exactly the same — just add one line.

## Manual Tracking

For custom tracking without the proxy:

```python
import llmlab

# Decorator
@llmlab.track_cost(provider="openai")
def my_function():
    response = client.chat.completions.create(...)
    return response

# Context manager
with llmlab.track() as tracker:
    tracker.log_call(model="gpt-4o", tokens=150, cost=0.003)

# Direct logging
llmlab.log_call(model="gpt-4o", tokens=150, cost=0.003)
```

## Unpatching

To temporarily bypass the proxy:

```python
from llmlab import unpatch

unpatch(openai)
# Calls now go directly to OpenAI
```

## Configuration

```python
from llmlab import set_config

set_config("api_key", "llmlab_pk_your_key")
set_config("backend_url", "https://api.llmlab.dev")
```

## Links

- [Dashboard](https://llmlab.dev)
- [GitHub](https://github.com/ArivunidhiA/llmlab)
- [Documentation](https://github.com/ArivunidhiA/llmlab#readme)
