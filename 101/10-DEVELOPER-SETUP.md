# Developer setup

## Prerequisites

- Git.
- Python 3.10–3.13. The package declares 3.10+, and CI currently tests 3.10,
  3.11, 3.12, and 3.13 across Linux, macOS, and Windows.
- A fresh virtual environment. The ignored `.venv` in this workspace is stale
  and its console script points at another absolute path. Use `.venv-review` (or
  another new name); do not reuse or delete the user's old environment.

Python 3.12 is a conservative default for local development because it is
inside the tested matrix and broadly supported by the optional dependencies.

## Install from this reviewed checkout

The public `main` branch and PyPI package still contain the legacy forecasting
product. This unreleased 0.3 source is not on a remote branch. Begin inside a
reviewed copy of the current workspace; restore ordinary clone instructions only
after a deliberate merge or release.

macOS/Linux:

```bash
cd "<path-to-reviewed-0.3-checkout>"
git rev-parse HEAD  # audited baseline begins 05482e41b958
python3.12 -m venv .venv-review
source .venv-review/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,forecast,llm]"
forecost --version
forecost --help
```

Windows PowerShell:

```powershell
Set-Location "<path-to-reviewed-0.3-checkout>"
git rev-parse HEAD  # audited baseline begins 05482e41b958
py -3.12 -m venv .venv-review
.venv-review\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,forecast,llm]"
forecost --version
forecost --help
```

Use the installed `forecost` command. `python -m forecost.cli` is not a
documented launcher and does not invoke the Click entry point by itself.

This dirty reviewed worktree contains post-baseline schema-v11/receipt-v2
repairs that are not on public `main`. A matching version string or successful
local install is not evidence that the public package contains them.

## Dependency extras

| Extra | Adds | When needed |
| --- | --- | --- |
| base install | Click, Rich, httpx | Current CLI and ledger core |
| `dev` | tests, lint, type, security, and Python package build tooling | Repository development; it does **not** install Twine or Check Wheel Contents |
| `forecast` | NumPy and statsmodels | Legacy forecast tests/features |
| `tui` | Textual and plotext | Legacy terminal UI |
| `llm` | Compatible LiteLLM line | LiteLLM callback and related tests |
| `mcp` | MCP 1.x compatible API | Optional read-only MCP server |
| `all` | All runtime extras | Broad runtime installation |

The `mcp` and `llm` versions are deliberately bounded in `pyproject.toml` for
API and wheel compatibility. Do not casually widen them without matrix tests.

## Optional MCP setup

```bash
python -m pip install -e ".[mcp]"
python -m forecost.mcp_launcher
```

The MCP server uses stdio, reads `ledger.db`, and exposes exactly three read-only
tools: `forecost_list_runs`, `forecost_get_receipt`, and
`forecost_compare_runs`. The last tool is a diagnostic that always abstains
without matched manifests. Full manifest evaluation remains a CLI-only
prototype; this MCP is not the proposed live budget/loop/recording surface.

## Claude plugin source boundary

Do not install the checked-in plugin into a production Claude profile while the
release hold is active. Its source launcher now executes only the exact
owner-controlled `$CLAUDE_PLUGIN_DATA/venv/bin/forecost-hook` and never searches
`PATH`; runtime package bootstrap is disabled. A future supported installer must
provision that environment through a reviewed, deterministic path. For now use
the fake-directory walkthrough in [Hands-on](11-HANDS-ON.md).

## Isolate developer data

Use a temporary absolute Forecost home when you do not want commands touching
your normal local state:

```bash
export FORECOST_HOME="$(mktemp -d)"
forecost doctor
forecost lab demo --ledger-path "$FORECOST_HOME/demo-ledger.db"
```

Run Lab accepts an explicit isolated ledger and is the safest first workflow.
`FORECOST_HOME` must be absolute and cannot contain parent traversal.

## Existing-state upgrade warning

Use synthetic copies for upgrade work. The schema migrator deliberately keeps
an exact pre-migration SQLite backup; that backup can retain raw cursor paths or
prompt identifiers written by an older version. Legacy `error.log`, hook,
outbox, and recovery files are also not globally rewritten by installation or a
schema bump. Current cursor hardening is lazy and usage/causal sources migrate
independently.

Do not point the current checkout at a real existing home and then infer that a
new schema version made all retained state content-minimizing. Inventory the
live home, exact backups, configured external paths, integration backups, and
exports separately. See [Data inventory](../docs/data-inventory.md#in-place-upgrade-truth).

## Baseline verification

```bash
pytest tests/ -v --tb=short
ruff check forecost/ tests/
ruff format --check forecost/ tests/
pyright
mypy forecost/
xenon forecost/ -b B -m A -a A
bandit -r forecost/ -c pyproject.toml
pip-audit
```

Run those commands with `.venv-review` activated. If Pyright is invoked through
an external/global wrapper instead, bind it explicitly to the project
interpreter with
`pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"` on a
POSIX shell. The repository no longer hardcodes an ignored local venv name.

Coverage/review gates:

```bash
pytest tests/ --cov=forecost --cov-report=term-missing --cov-report=xml
diff-cover coverage.xml --compare-branch=origin/main --fail-under 90
```

## Build verification

Twine and Check Wheel Contents are release-QA tools used by the workflow but
are not members of the `dev` extra. Install them explicitly in the isolated
review environment before running the commands below:

```bash
python -m pip install twine check-wheel-contents
python -m build
twine check dist/*
check-wheel-contents dist/*.whl
python scripts/check_release.py
```

For a release rehearsal, resolve those tools through the same reviewed
constraints or lock used by CI rather than treating an unpinned local install as
reproducible release evidence.

`python scripts/check_release.py --tag v0.3.0` is expected to reject the
current tree while `CHANGELOG.md` says `Unreleased`. Do not “fix” this by
changing release state without maintainer approval.

## Common setup problems

### `forecost` imports from the wrong checkout

```bash
which forecost          # Windows: Get-Command forecost
python -m pip show forecost
python -m pip check
```

If a copied environment has a stale shebang or PATH selects a global install,
delete only that project virtual environment, create a fresh one, and reinstall
editable dependencies.

### MCP tests fail during collection

Install the optional MCP extra: `python -m pip install -e ".[dev,mcp]"`.
The base package intentionally does not require MCP.

### A dependency conflicts with a global tool

Use a clean project venv. Do not repair unrelated global packages as part of a
Forecost change.

### A write failed or the database looks stale

Start with:

```bash
forecost doctor --json
forecost recover
forecost verify
forecost privacy verify --help
```

Read command help before schema migration or purge operations.
