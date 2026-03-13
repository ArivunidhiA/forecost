# Contributing to llmlab

Thanks for your interest in contributing to llmlab.

## Development Setup

```bash
git clone https://github.com/ArivunidhiA/llmlab.git
cd llmlab
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

## Code Style

We use ruff for linting and formatting:

```bash
ruff check llmlab/ tests/
ruff format llmlab/ tests/
```

## Pull Request Process

1. Fork the repo and create a feature branch
2. Make your changes with tests
3. Ensure `ruff check` and `pytest` pass
4. Submit a PR against `main`

## Reporting Issues

Use the GitHub issue templates for bugs and feature requests.
