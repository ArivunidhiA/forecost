# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-03-12

### Changed
- **Branding:** PyPI package, CLI, and Python import are **`forecost`**. Project config is **`.forecost.toml`**; local data lives under **`~/.forecost/`**. Disable tracking with **`FORECOST_DISABLED=1`** (replaces older env var names).

### Added
- `forecost init` -- Initialize project with heuristic or LLM-powered scope analysis
- `forecost forecast` -- Adaptive exponential smoothing cost forecast with Rich output
- `forecost status` -- One-line project status
- `forecost track` -- View recent tracked LLM calls
- `forecost serve` -- Local HTTP API server
- `forecost demo` -- See forecost in action with sample data
- `forecost watch` -- Live cost dashboard in terminal
- `forecost optimize` -- Model optimization suggestions
- `forecost reset` -- Reset project baseline or full data
- `auto_track()` -- Zero-code-change cost tracking via httpx interception
- `log_call()` -- Manual cost logging
- `log_stream_usage()` -- Streaming response cost logging
- `@track_cost` decorator for function-level tracking
- `FORECOST_DISABLED` environment variable to disable tracking
- `forecost.disable()` function
- Support for 90+ models across OpenAI, Anthropic, Google, Mistral, DeepSeek, xAI, Meta, Cohere
- Self-correcting pricing via ratio-based forecasting
- Forecast stability metric (replaces misleading MAPE)
- Budget alerts and CI exit codes (`--exit-code`)
- Optional Textual TUI dashboard (`pip install forecost[tui]`)
- PEP 561 py.typed marker for type checking support
