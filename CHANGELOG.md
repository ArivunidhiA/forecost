# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-03-12

### Added
- `llmcast init` -- Initialize project with heuristic or LLM-powered scope analysis
- `llmcast forecast` -- Adaptive exponential smoothing cost forecast with Rich output
- `llmcast status` -- One-line project status
- `llmcast track` -- View recent tracked LLM calls
- `llmcast serve` -- Local HTTP API server
- `llmcast demo` -- See llmcast in action with sample data
- `llmcast watch` -- Live cost dashboard in terminal
- `llmcast optimize` -- Model optimization suggestions
- `llmcast reset` -- Reset project baseline or full data
- `auto_track()` -- Zero-code-change cost tracking via httpx interception
- `log_call()` -- Manual cost logging
- `log_stream_usage()` -- Streaming response cost logging
- `@track_cost` decorator for function-level tracking
- `LLMLAB_DISABLED` environment variable to disable tracking
- `llmcast.disable()` function
- Support for 90+ models across OpenAI, Anthropic, Google, Mistral, DeepSeek, xAI, Meta, Cohere
- Self-correcting pricing via ratio-based forecasting
- Forecast stability metric (replaces misleading MAPE)
- Budget alerts and CI exit codes (`--exit-code`)
- Optional Textual TUI dashboard (`pip install llmcast[tui]`)
- PEP 561 py.typed marker for type checking support
