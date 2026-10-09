# Recovery verification — 2026-10-09

Scope: the 0.3.0 product-core worktree recovered from the laptop-transfer archive
(branch `recovery/product-core-0.3`). Verified from a clean venv and from the built
wheel installed into a second clean venv (real CLI, no mocks on the critical path).

## Defects found and fixed
1. `tests/test_comparison.py` fixtures used a rate-less tariff, so 5 `compare` tests
   failed after `comparison.py` began recomputing list-rate amounts. Fixtures now carry
   `output_rate_micros` and a consistent meter quantity.
2. CI gates failed on `forecost/comparison.py`: `ruff format`, xenon (3 blocks ranked C/D),
   bandit B608/B105. Refactored into small helpers; identifiers are quoted.
3. Legacy SDK/`costs.db` persisted raw project paths, full project names, and arbitrary
   metadata. New rows now store a keyed pseudonym, a basename, and bounded scalar metadata.
4. Regression found by E2E and fixed: `forecost migrate` crashed on pseudonymized paths.
   Pseudonymized rows migrate without a workspace; malformed rows are counted, not fatal.
5. `claude-sonnet-4-5`, `claude-opus-4-5`, `claude-opus-4-1`, `claude-3-7-sonnet` were
   priced by guess. Explicit rows added (list rates, not re-verified against live docs).

6. Pricing re-verified against the live Anthropic pricing page (2026-10-09). Fable 5 ($10/$50)
   and Opus 4.8 ($5/$25) were correct. Sonnet 5 is now permanently $2/$10 (the table still
   moved it to $3/$15 after 2026-08-31, overstating spend); fixed. Added Fable 5.1, Mythos 5.1,
   Opus 5, Opus 5.5, Sonnet 5.5. Haiku 5.5 is context-tiered and stays deliberately unpriced.
7. `forecost legacy scrub` rewrites pre-hardening `costs.db` rows in place; `doctor` reports
   remaining raw rows. Canary tests cover `costs.db` dumps.
8. Linux: the Claude hook launcher used BSD `stat -f`, which on GNU prints filesystem status, so
   ownership checks failed and hooks silently never ran. GNU `stat -c` is now tried first.
9. Windows: `os.fchmod` was unavailable and `os.open` lacked `O_BINARY` (corrupting the
   installation key and byte-offset cursors). Both fixed; POSIX-only tests are skipped there.
10. CI now runs on pushes to feature branches, reports all failures (no `-x`), and runs
    `scripts/e2e_wheel_smoke.py` against the built wheel on Linux and macOS.

## Evidence
- pytest: 655 passed locally (macOS, all extras); GitHub CI green on Linux, macOS and Windows
  for Python 3.10-3.13, plus lint, security, diff-coverage (90%) and wheel smoke jobs.
- Linux also reproduced in a python:3.12 container (634 passed at the time).
- pytest (earlier run): 625 passed, 1 skipped. ruff check/format, pyright, xenon (B/A/A), bandit: clean.
- `twine check` on sdist and wheel: passed. Wheel ships plugin assets.
- Installed-wheel journeys: `lab demo`, `ingest` (idempotent on re-run), `ledger status`,
  `reconcile`, `pricing-audit` (no guessed models after fix), `burn`, `privacy verify`,
  `doctor`, hooks fail-open on garbage input, legacy `init` + SDK `log_call`, `migrate`
  (idempotent), `compare` abstain/invalid exit codes.
- Privacy canary planted in a transcript prompt/reply and cwd: absent from the Forecost home.

## Not verified / known risk
- Release stays on the 2026-08-13 hold: no independent privacy/security review, no live
  provider samples, no sanitizer for pre-hardening artifacts, legacy rows written by earlier
  versions keep raw values until purged.
- OpenAI/Gemini/other pricing rows last verified March 2026.
- Live LiteLLM gateway traffic was not exercised (adapter unit tests only). MCP tests pass with
  the `mcp` extra installed locally but CI does not install that extra.
- Dependency advisories: pip-audit reported only tooling `pip`.

Verdict: GO WITH KNOWN RISK for continued internal/controlled-trial work; NO-GO for public release.
