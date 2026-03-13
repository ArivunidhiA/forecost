# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-03-12

### Added
- `llmlab init` -- Initialize project with heuristic or LLM-powered scope analysis
- `llmlab forecast` -- Adaptive exponential smoothing cost forecast with Rich output
- `llmlab status` -- One-line project status
- `llmlab track` -- View recent tracked LLM calls
- `llmlab serve` -- Local HTTP API server
- `llmlab demo` -- See llmlab in action with sample data
- `llmlab watch` -- Live cost dashboard in terminal
- `llmlab optimize` -- Model optimization suggestions
- `llmlab reset` -- Reset project baseline or full data
- `auto_track()` -- Zero-code-change cost tracking via httpx interception
- `log_call()` -- Manual cost logging
- `log_stream_usage()` -- Streaming response cost logging
- `@track_cost` decorator for function-level tracking
- `LLMLAB_DISABLED` environment variable to disable tracking
- `llmlab.disable()` function
- Support for 90+ models across OpenAI, Anthropic, Google, Mistral, DeepSeek, xAI, Meta, Cohere
- Self-correcting pricing via ratio-based forecasting
- Forecast stability metric (replaces misleading MAPE)
- Budget alerts and CI exit codes (`--exit-code`)
- Optional Textual TUI dashboard (`pip install llmlab[tui]`)
- PEP 561 py.typed marker for type checking support
