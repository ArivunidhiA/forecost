# Production bar — the gates before Forecost goes public

Owner decision (2026-10-10): nothing is published (no PyPI upload, no release, no announcement)
until every gate below is green and an adversarial review finds nothing. "Green" means measured
by an automated check or a dated artifact in this repo, not an assertion.

| # | Gate | How it is measured | Status |
|---|------|--------------------|--------|
| 1 | Correctness of money | Pricing rows match provider pages; refreshed weekly; >4x moves held; tiers modeled | automated (pricing-refresh) |
| 2 | Accuracy of counting | One event per API response; idempotent; order/duplicate invariant; cost additive | property-tested (`tests/test_adversarial.py`) |
| 3 | Robustness | Fuzzed transcripts + hook payloads never crash/hang; hooks always exit 0 | fuzzed 500 ex/property; weekly deep run |
| 4 | Privacy | Planted canaries never reach any persisted byte (ledger, logs, spools, legacy DB) | canary tests + fuzz |
| 5 | Platform | Linux/macOS/Windows x Py 3.10-3.13; built-wheel E2E smoke | CI |
| 6 | Static quality | ruff, pyright, mypy, xenon B/A/A, bandit, diff-coverage >= 90% | CI |
| 7 | Drift control | `compare` decisions pinned by golden snapshot; strictness changes need test changes | CI guard |
| 8 | Mutation strength | Surviving-mutant rate on pricing, ledger, ingest, privacy modules below an agreed ceiling | **open** (baseline not yet measured) |
| 9 | Live-runtime truth | Reconcile ingested spend against provider-reported usage on real sessions (owner-approved samples) | **open** (needs real sessions) |
| 10 | Independent review | Outside privacy/security review of the repaired code; findings closed | **open** (external) |
| 11 | Demand | Matched-run gate in docs/status.md | **open** (needs real users) |

Gates 8-11 are the remaining work. 1-7 are enforced continuously.
