# Contributing to forecost

Thanks for your interest in contributing to forecost. The highest-value
contribution is a trustworthy adapter for another agent harness or billing
source; the checklist below is designed to make one reviewable in under an
hour without sharing private transcripts.

## Development Setup

```bash
git clone https://github.com/ArivunidhiA/forecost.git
cd forecost
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,forecast,llm]"
```

## Running Tests

```bash
pytest tests/ -v --tb=short
pyright
xenon forecost/ -b B -m A -a A
bandit -r forecost/ -c pyproject.toml
```

## Code Style

We use ruff for linting and formatting:

```bash
ruff check forecost/ tests/
ruff format forecost/ tests/
```

## Pull Request Process

1. Fork the repo and create a focused branch.
2. Make the smallest change that proves the behavior, with tests.
3. Run the checks above; CI also runs Python 3.10–3.13 on Linux, macOS, and Windows.
4. Explain the data source, identity rule, failure behavior, and privacy impact.
5. Submit a PR against `main`.

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

The ledger is local-first and content-free. Hook failures are fail-open. Writes
are atomic and recoverable. The estimator remains shadow-only until independent
held-out evidence clears its published gates. A change that weakens one of these
laws needs an explicit design discussion, not just a passing test.

## Reporting Issues

Use the GitHub issue templates for bugs, adapter requests, and feature requests.
Do not attach raw transcripts or `~/.forecost` databases; reduce reports to a
synthetic fixture whenever possible.
