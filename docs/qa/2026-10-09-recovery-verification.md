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

## Evidence
- pytest: 625 passed, 1 skipped. ruff check/format, pyright, xenon (B/A/A), bandit: clean.
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
- MCP server, LiteLLM live gateway, Windows/Linux matrix, and the dependency-advisory
  refresh were not exercised here (pip-audit reported only tooling `pip`).

Verdict: GO WITH KNOWN RISK for continued internal/controlled-trial work; NO-GO for public release.
