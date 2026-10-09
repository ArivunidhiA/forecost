# Frozen installed-artifact findings

**Frozen:** 2026-08-09 after installing the first clean-commit wheel
`f1ff47509d8a99bb2c34f039baf62621b096c0862865266d0aa54dbaa8dba85a`.

## IF-001 — Wheel omitted required Claude plugin assets

**Severity:** release blocker  
**Interface evidence:** installed `forecost setup claude --dry-run` failed with
`plugin package is incomplete`; `forecost self-test claude --json` failed with
`cannot read packaged Claude plugin`.  
**State evidence:** wheel inspection found zero `plugin/` assets while both
commands resolve their default plugin root relative to the installation.  
**Oracle:** a supported base-wheel command must either carry the assets it
requires or declare/install a separate artifact; it may not be broken at first
use.

**Required repair:** include the reviewed plugin package in the wheel, resolve
source-tree and installed roots deterministically, assert manifest/version and
executable contents, then rerun setup/apply/check/self-test/uninstall from the
installed artifact.

## Harness correction — not a product defect

The first command wrote `demo.txt` inside a new custom `FORECOST_HOME` before
Forecost initialized it. The product correctly rejected that nonempty unmarked
directory under its destructive-safety rule, but the unhandled stack trace is a
future UX improvement. Final QA keeps logs outside the data root and begins
with an empty directory.

The temporary environment used `--system-site-packages` to remain offline, so
it inherited an unrelated global Forecost 0.2 installation and a `wily`/`radon`
conflict. The wheel's local 0.3 package won import precedence, but final evidence
must distinguish artifact behavior from host dependency-resolution evidence.
