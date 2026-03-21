# Contributing to forecost

Thanks for your interest in contributing to forecost.

## Development Setup

```bash
git clone https://github.com/ArivunidhiA/forecost.git
cd forecost
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
ruff check forecost/ tests/
ruff format forecost/ tests/
```

## Pull Request Process

1. Fork the repo and create a feature branch
2. Make your changes with tests
3. Ensure `ruff check` and `pytest` pass
4. Submit a PR against `main`

## Reporting Issues

Use the GitHub issue templates for bugs and feature requests.
