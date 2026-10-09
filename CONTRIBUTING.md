# Contributing to forecost

Thanks for your interest in contributing to forecost. The highest-value
contribution is a trustworthy adapter for another agent harness or billing
source; the checklist below is designed to make one reviewable in under an
hour without sharing private transcripts.

If this is your first time in the repository, read
[`101/README.md`](101/README.md) before making changes. It explains the current
receipt product, the parallel evidence lanes in `ledger.db`, and the boundary
between current and legacy code.

## Development Setup

The public `main` branch is still the legacy product. For this unreleased 0.3
work, start in the reviewed local checkout. Its existing ignored `.venv` is stale
and has an absolute shebang to another directory, so create a fresh environment
with a distinct name:

```bash
cd "<path-to-reviewed-0.3-checkout>"
python -m venv .venv-review
source .venv-review/bin/activate
pip install -e ".[dev,forecast,llm]"
```

## Running Tests

```bash
pytest tests/ -v --tb=short
pyright
mypy forecost/
xenon forecost/ -b B -m A -a A
bandit -r forecost/ -c pyproject.toml
```

## Code Style

We use ruff for linting and formatting:

```bash
ruff check forecost/ tests/
ruff format --check forecost/ tests/
```

## Pull Request Process

1. Fork the repo and create a focused branch.
2. Make the smallest change that proves the behavior, with tests.
3. Run the checks above; CI also runs Python 3.10–3.13 on Linux, macOS, and Windows.
4. Explain the data source, identity rule, failure behavior, and privacy impact.
5. Submit against the maintainer-selected integration branch; do not assume the
   current legacy `main` is ready for this code.

## Adding an agent adapter

Start from `forecost/adapters/base.py` and the synthetic fixtures in
`tests/test_adapters_claude_code.py`. An adapter is ready when it satisfies all
of these contracts:

- one provider response maps to one stable `event_uid` across retries;
- a cursor advances only after the sink accepts the event;
- torn or malformed input is retried or reported, never silently discarded;
- metadata contains bounded operational scalars only—no prompts, completions,
  tool arguments/output, file contents, or arbitrary nested objects;
- source-reported and pricing-table valuations remain separate postings;
- an unknown or guessed price is labeled and cannot cause a hard budget denial;
- tests cover idempotency, resume, partial input, sink failure, and the privacy
  canary without using a real user transcript.

Please open an Adapter Request issue before a large implementation so maintainers
can agree on identity and provenance first.

## Product laws

The ledger is local-first and is intended to satisfy a field-allowlisted,
content-excluding persistence contract for current-ledger surfaces. The current
worktree installation-keys cursor/error identities, verifies transcript
replacement, streams privacy scans, and covers the known default-home state in
the purge manifest. The unsupported legacy `costs.db` still permits legacy
project configuration and is not covered by that stronger contract; custom
state deliberately placed outside `FORECOST_HOME` is not discoverable by
`purge`. Hook failures are fail-open. Canonical SQLite uses WAL,
`synchronous=FULL`, verified Backup API migration snapshots, and idempotent
recovery, but those mechanisms still rely on honest OS/storage behavior and do
not resist a same-user rewrite. The estimator remains shadow-only until independent
held-out evidence clears its published gates. A change that weakens one of these
laws needs an explicit design discussion, not just a passing test.

## Reporting Issues

Use the GitHub issue templates for bugs, adapter requests, and feature requests.
Do not attach raw transcripts or `~/.forecost` databases; reduce reports to a
synthetic fixture whenever possible.
