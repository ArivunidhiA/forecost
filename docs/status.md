# Forecost status — 2026-08-02

## Current product state

- **Experimental local:** graph-aware run receipts, deterministic offline Run
  Lab, offline JSON/CSV provider/gateway/OTel import, aggregate reconciliation,
  and single-host resource envelopes.
- **Observed only:** Claude Code transcript and LiteLLM adapters. They do not
  provide full graph identity or a bounded provider-side overrun.
- **Not claimed:** live provider billing API ingestion, provider-billed cost
  without an imported export, distributed/resource-provider enforcement,
  hosted control plane, or task-cost forecasting.

## Earlier audit closure

- Completed the four-lens production audit and consolidated it in
  `docs/audit-1.md`.
- Remediated every P0 integrity, destructive-safety, guessed-price policy,
  recovery, plugin-bootstrap, and local CI blocker.
- Aligned the repository around the local, content-free agent cost ledger;
  refreshed README, architecture, contribution, security, release, and issue
  surfaces.
- Verified 366 tests plus one intentional skip, 92% changed-line coverage,
  Ruff/format/Pyright/Xenon, Bandit, a fresh-resolution `pip-audit`, Twine,
  wheel contents, and an outside-repository wheel install.
- Closed the final security re-audit: open-ended identifiers and recovery
  posting text are irreversibly normalized at sink boundaries; malformed
  postings cannot partially persist; unowned custom data roots are rejected
  without changing files, modes, inodes, timestamps, or markers.
- Measured minimal-wheel median startup at 29.5 ms (`--help`) and 36.3 ms
  (`ledger status`) on the audit host.
- Re-ran the 12-thread/3,600-event integrity probe: all 3,600 events were
  accepted with zero exceptions, orphan events, or duplicate posting keys.

## Release evidence

- GitHub Actions run `30758731742` is fully green: lint, security, diff coverage,
  12 Python/OS test jobs, and built-wheel/plugin smoke on Linux and macOS.
- No local release blockers remain after the final independent security,
  architecture, and test/performance closure reviews.

## Deliberately not published

- The 0.3.0 changelog remains `Unreleased`, and the release validator refuses a
  `v0.3.0` publish until that marker is replaced with a date.
- No PyPI release, GitHub release, PR merge, or release tag was created by this
  audit. Publication is a distinct maintainer-controlled action after remote CI
  is green.

## Next product gates

1. Add real provider export conformance fixtures from willing operators; do not
   add live HTTP before the input/authority contract is proven.
2. Migrate MCP reads to receipt/ledger queries and retire legacy HTTP surfaces.
3. Benchmark aggregate reconciliation and reservation admission at 100k+ facts.
4. Publish adapter conformance fixtures, then add runtime adapters against the
   documented conversation/trace/run/span contract.
5. Add SBOM/provenance and protect main, release tags, and PyPI before publish.
