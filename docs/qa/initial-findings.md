# Frozen initial QA findings

**Frozen:** 2026-08-09 after the first integrated source/static/performance pass.  
**Artifact state:** source branch plus locally built predecessors; clean final
wheel QA had not yet run.  
**Rule:** this file is immutable evidence of the first pass. Repairs and rerun
results belong in `final-report.md`.

## Positive evidence

- The integrated source suite completed with **429 passed, 1 skipped** in
  16.63s. This included property, multi-process, tamper, adapter, migration,
  privacy, CLI, packaging metadata, and benchmark tests.
- Focused agent slices independently reported green tests and type/lint checks.
- 40k, 100k, and 250k graph receipts rendered successfully; 250k completed in
  3.51s on the QA host.
- A 1,020,000-observation ingest completed and fixed-size admission stayed flat
  across the history matrix.

These are source/state oracles, not a release verdict.

## Findings frozen before final repair

### F-001 — Reconciliation supersession lookup became quadratic at charge density

**Severity:** release blocker  
**Evidence:** a million-span/20k-charge run spent 162.53s in reconciliation; a
direct 20k-charge probe reproduced 157.36s. The active-charge query lacked an
index on `supersedes_charge_id`, and match classification used repeated scans.

**Required repair:** index supersession and authority/fact access, use set-key
joins, rerun the same density probe, and retain an explicit full-receipt size
boundary.

### F-002 — Full million-node receipt has no bounded user interface

**Severity:** known product risk / unsupported boundary  
**Evidence:** million-observation ingest was exercised, but a full million-span
portable receipt was intentionally not built because the artifact itself is
unbounded. The measured full graph boundary was 250k spans.

**Required repair:** do not claim million-span full receipts. Add an explicit
limit and, before future support, a streaming summary/export interface.

### F-003 — Static formatting gate failed

**Severity:** release blocker  
**Evidence:** `ruff format --check forecost tests scripts` reported 18 files
requiring formatting.

**Required repair:** format the tree, rerun tests, and keep format check in the
clean-artifact gate.

### F-004 — MyPy exposed current-path and legacy typing errors

**Severity:** release blocker for the configured gate  
**Evidence:** 16 errors across receipt/run commands, recovery, LiteLLM optional
imports, TUI/interceptor, scope, and optional legacy commands.

**Required repair:** fix actual current-path types; explicitly model missing
optional imports; do not silence current receipt/resource/adapter modules.

### F-005 — Complexity gate failed on new trust-critical functions

**Severity:** release blocker  
**Evidence:** Xenon found C–E blocks in receipt construction, reconciliation,
resource reservation/splitting, integrity verification, contracts, adapters,
and Claude commands; several modules ranked B when the configured module gate
was A.

**Required repair:** decompose behavior-preserving typed helpers and meet the
existing B-block/A-module gate. Do not weaken thresholds.

### F-006 — Security scan required code-level disposition

**Severity:** release blocker until classified  
**Evidence:** Bandit reported explicit subprocess execution, deterministic RNG,
and static SQL composition. No high-severity result was present, but the scan
exited nonzero.

**Required repair:** keep `shell=False`, fixed launchers, and explicit user
command semantics; eliminate dynamic SQL where practical and add only narrow,
reviewed suppressions whose comments state the invariant.

### F-007 — Dead-code scan found callback protocol parameters

**Severity:** minor  
**Evidence:** Vulture reported unused LiteLLM callback parameters required by the
upstream callback signature.

**Required repair:** explicitly consume/delete protocol-only parameters so the
signature remains compatible and the intent is inspectable.

### F-008 — Obsolete real-SDK script violated offline QA scope

**Severity:** release blocker  
**Evidence:** `scripts/test_real_sdk.py` invited use of real API keys, network,
and paid calls, and failed repository-wide lint. It did not test the canonical
offline adapter protocol.

**Required repair:** remove it; use SDK-independent golden mappings and stage
live account validation as founder/field work.

### F-009 — Development virtual environments were relocated/stale

**Severity:** environment risk  
**Evidence:** console scripts in `.venv`/`.venv312` referenced an older absolute
checkout path. Module invocation worked, but direct `pytest`/`pyright` scripts
failed. The host environment also contained an unrelated `wily`/`radon`
dependency conflict.

**Required repair:** use `python -m` during this run and prove behavior in a new
temporary installed-wheel environment. Do not treat host `pip check` as the
artifact's dependency result.

### F-010 — Clean installed-artifact and upgrade journeys still unproven

**Severity:** release blocker  
**Evidence:** the first pass was primarily source-tree execution. Exact wheel
entry points, isolated Claude setup, empty home, offline imports, legacy schema
upgrade, SBOM/provenance, and privacy/integrity mutation journeys still needed
three-layer evidence through the installed artifact.

**Required repair:** build from clean committed state, install the wheel in an
empty temporary environment, freeze command/state/oracle logs, and rerun after
all source repairs.

## First-pass disposition

The first pass is **not releasable**. The final report must show each repair or
carry the item as a named known risk, then issue exactly one verdict from the QA
profile vocabulary.
