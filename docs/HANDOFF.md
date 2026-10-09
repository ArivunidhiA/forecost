# Forecost handoff — 2026-10-09

## State
- `main` = the 0.3.0 product-core (merged via PR #3). Status stays **UNRELEASED EXPERIMENTAL**:
  no tag, no PyPI upload. PyPI still serves the legacy 0.1.1.
- All CI green on Linux/macOS/Windows (Py 3.10-3.13), lint (ruff, pyright, mypy, xenon), security
  (bandit), diff-coverage >= 90%, built-wheel E2E smoke (`scripts/e2e_wheel_smoke.py`).
- Every finding in the July deep audit (docs: `FORECOST_DEEP_AUDIT_2026-07-17.md` in the archive)
  is fixed and tested: requestId dedupe (no 2.25x inflation), session-window estimate join,
  global-shrinkage estimator, torn-line cursor, private file modes, untrusted repo policy,
  drain-barrier flush, run-scope rejection, LiteLLM tests in CI.

## Self-maintaining systems
- `.github/workflows/pricing-refresh.yml`: weekly refresh of `forecost/data/pricing.json`
  (gates: >4x jumps held, full tests, auto PR + merge) and a freshness alarm (>45 days).
- `forecost pricing-update`: opt-in https refresh into `$FORECOST_HOME` (only network call).
- Comparison guard: `tests/golden/compare_v1.json` + `scripts/check_comparison_guard.py` (PRs).
- Dependabot is active; review its PRs (#6-#8 at time of writing) rather than blind-merging
  major bumps of GitHub Actions.

## Still gated (cannot be automated)
1. Independent privacy/security review of the repaired implementation.
2. Live provider/runtime samples (authenticated billing, real Claude/LiteLLM traffic).
3. Matched-run demand gate (`docs/status.md`, "Product-validation gates").
4. Pre-hardening artifacts outside `FORECOST_HOME` (old backups) stay raw.
5. Pricing covers context tiers, but not batch/priority/flex service tiers, audio modalities, or regional uplifts.

## Releasing (when 1-3 are satisfied)
Do NOT paste a token into chat. Preferred: PyPI Trusted Publishing for this GitHub repo
(pypi.org -> project forecost -> Publishing -> add GitHub publisher: owner ArivunidhiA, repo
forecost, workflow `release.yml`), then push a `v0.3.0` tag. Fallback: create an API token at
pypi.org -> Account settings -> API tokens (scope: project forecost), store in `~/.pypirc`, run
`python -m twine upload dist/forecost-0.3.0*` yourself. Also confirm the PyPI project is under
your control first (the plugin bootstrap installs from it).

## Prompt for a new chat
> Read docs/HANDOFF.md and docs/status.md in github.com/ArivunidhiA/forecost (main). Verify the
> current state (run the test suite and `python scripts/e2e_wheel_smoke.py` against a built
> wheel), then review open Dependabot PRs and the latest `Pricing refresh` run. Work only on the
> items under "Still gated" that can be advanced in code; do not tag or publish.
