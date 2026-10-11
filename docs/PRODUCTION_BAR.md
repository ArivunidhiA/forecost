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
| 8 | Mutation strength | `scripts/mutation_check.py`: killed-mutant rate on money/privacy modules (equivalent mutants excluded) | pricing 98%, pricing_data ~98%, db sanitizer/scrub ~90%, usage merge + stream merge ~95% (2026-10-10); extend to comparison/ledger kernel |
| 9 | Live-runtime truth | `scripts/verify_ingest_accuracy.py`: independent recount of real transcripts vs ledger | **exact match on 6,050 real responses / 250 sessions** (tokens by class). Billing-side truth (provider invoice) still open |
| 10 | Independent review | Outside privacy/security review of the repaired code; findings closed | **open** (external) |
| 11 | Demand | Matched-run gate in docs/status.md | **open** (needs real users) |

Gates 8-11 are the remaining work. 1-7 are enforced continuously.

## Findings log
- 2026-10-10: gate 9 recount found output tokens undercounted ~73% on real sessions (streamed
  responses logged as several records; first-record-wins kept the partial). Fixed with cumulative
  merge; independent recount now exact. Lesson: an independent check must not share the
  implementation's assumptions - the first recount reused first-wins and agreed with the bug.
