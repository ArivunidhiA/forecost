# CONTRIBUTING.md

## Contributing to forecost

Thanks for your interest in contributing to forecost.

---

## Development Setup

```bash
git clone https://github.com/ArivunidhiA/forecost.git
cd forecost
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Running Tests

```bash
pytest tests/ -v
```

With coverage:
```bash
pytest tests/ --cov=forecost --cov-report=html
```

---

## Code Style

We use ruff for linting and formatting:

```bash
ruff check forecost/ tests/
ruff format forecost/ tests/
```

Configuration in `pyproject.toml`:
- Target: Python 3.10+
- Line length: 100
- Enabled rules: E, F, I, W (pycodestyle, Pyflakes, isort, pydocstyle warnings)

---

## Pull Request Process

1. Fork the repo and create a feature branch
2. Make your changes with tests
3. Ensure `ruff check` and `pytest` pass
4. Submit a PR against `main`

---

## Reporting Issues

Use the GitHub issue templates for bugs and feature requests.

---

## Development Guidelines

### Adding a New CLI Command

1. Create `forecost/commands/mycommand_cmd.py`:
   ```python
   import click

   @click.command(name="mycommand")
   @click.option("--flag", is_flag=True)
   def mycommand(flag):
       """Command description."""
       pass
   ```

2. Import and register in `forecost/cli.py`:
   ```python
   from forecost.commands.mycommand_cmd import mycommand
   main.add_command(mycommand)
   ```

3. Add tests in `tests/test_commands.py`:
   ```python
   def test_mycommand(cli_runner):
       result = cli_runner.invoke(main, ["mycommand"])
       assert result.exit_code == 0
   ```

### Adding a New Model to Pricing

Edit `forecost/pricing.py`:

```python
FALLBACK_PRICING = {
    # ... existing models ...
    "new-model-name": {"input": 1.50, "output": 2.00},
}
```

Add to appropriate tier in `MODEL_TIERS` if applicable.

### Database Migrations

forecost uses auto-migration for simple schema changes:

```python
def get_or_create_db():
    # ... existing schema creation ...
    cols = [r[1] for r in conn.execute("PRAGMA table_info(table_name)").fetchall()]
    if "new_column" not in cols:
        conn.execute("ALTER TABLE table_name ADD COLUMN new_column TEXT DEFAULT 'default'")
        conn.commit()
```

For complex migrations, document manual steps in CHANGELOG.

---

## Project Structure for Contributors

```
forecost/
├── forecost/
│   ├── __init__.py          # Public API exports
│   ├── cli.py               # CLI entry point
│   ├── db.py                # SQLite persistence
│   ├── forecaster.py        # Ensemble forecasting
│   ├── interceptor.py       # httpx patching
│   ├── pricing.py           # Model pricing database
│   ├── scope.py             # Project scope analysis
│   ├── tracker.py           # Public tracking API
│   ├── tui.py               # Textual dashboard
│   └── commands/            # CLI commands
│       ├── __init__.py
│       ├── calc_cmd.py
│       ├── demo_cmd.py
│       ├── export_cmd.py
│       ├── forecast_cmd.py
│       ├── init_cmd.py
│       ├── optimize_cmd.py
│       ├── price_cmd.py
│       ├── reset_cmd.py
│       ├── serve_cmd.py
│       ├── status_cmd.py
│       ├── track_cmd.py
│       └── watch_cmd.py
├── tests/                   # Test suite
└── .github/workflows/       # CI/CD
```

---

## Testing Philosophy

- **Unit tests** for individual functions (test_forecaster.py)
- **Integration tests** for CLI commands (test_commands.py)
- **Mock external services** - never hit real APIs in tests
- **Use tmp_path** for isolated database files
- **Reset global state** - session stats, interceptor state

---

## Release Process (Maintainers)

1. Update `CHANGELOG.md` with new version
2. Update `__version__` in `forecost/__init__.py`
3. Commit and push: `git commit -m "Release 0.X.Y"`
4. Create GitHub Release with version tag
5. CI automatically publishes to PyPI
