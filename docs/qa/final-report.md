# Forecost 0.3.0 packaged-product QA report

> **Historical and superseded for release decisions.** This report accurately
> records the 2026-08-09 packaged test pass, but the 2026-08-13
> [status](../status.md) and
> [red team](../research/2026-08-13-startup-grade-red-team-v2.md) found new P0
> defects. The current worktree contains later internal remediations, but this
> older artifact was not rerun against them and no external review or live
> validation has occurred. Its “GO WITH KNOWN RISK,” content-free,
> complete-evidence, critical-path, migration-backup, purge, authority, and
> integrity conclusions must not be used to justify publication.

**Date:** 2026-08-09  
**Branch:** `codex/forecost-product-core`  
**QA target:** founder review of the local, content-free economic-receipt core;
publication remains a separate founder action.

## Artifact under test

- Wheel: `forecost-0.3.0-py3-none-any.whl`
- Wheel SHA-256:
  `49b6e822453d60e56aaa2df2840e81d2980a9ce681bc8610c0fe7e25901262f6`
- Build mode: local, offline, deterministic timestamp, clean committed source.
  The generated provenance records the exact source commit and both artifact
  hashes; they are not embedded here because this report is itself part of the
  source distribution.
- Metadata: Twine passed; wheel paths and entry points passed custom inspection;
  the five required Claude plugin assets are present.

## Frozen finding dispositions

| Finding | Disposition | Repair evidence |
|---|---|---|
| F-001 | Repaired | Supersession/authority indexes and set joins reduced the 20k-charge probe from about 157 s to about 0.30 s. |
| F-002 | Boundary retained | Full graph receipts are supported through the measured 250k boundary; a million-node portable receipt is not claimed. |
| F-003 | Repaired | Repository formatting and Ruff checks pass. |
| F-004 | Repaired | MyPy passes across 93 source files; Pyright reports zero errors. |
| F-005 | Repaired | Xenon passes the unchanged strict B-block/A-module/A-average thresholds. |
| F-006 | Repaired | Bandit reports zero findings after narrow, invariant-documented dispositions. |
| F-007 | Repaired | Protocol-only callback parameters are explicitly consumed; Vulture passes. |
| F-008 | Repaired | The paid/network real-SDK script was removed; adapters use local fixtures. |
| F-009 | Isolated | QA used module invocation and a new installed-wheel environment; the unrelated host `wily`/`radon` conflict is not attributed to the artifact. |
| F-010 | Repaired | Clean and upgrade journeys passed through the installed 0.3.0 CLI; checksums, SBOM, and unsigned provenance were generated. |
| IF-001 | Repaired | The rebuilt wheel contains the plugin manifest, hook manifest, bootstrap and launcher scripts; dry-run/apply/check/self-test/uninstall passed. |

## Three-layer evidence

| Journey | Interface | State | Independent oracle |
|---|---|---|---|
| First synthetic receipt | `lab demo`, `runs`, and three receipt renderers succeeded | Canonical ledger contained a complete causal run and chained journal | JSON, text, and Markdown agreed on run ID, timing, amount, and digest |
| Empty/degraded input | Empty history returned guidance; malformed OTel returned a bounded error and exit 1 | No malformed observation was committed | Ledger verification remained intact |
| Upgrade | Dry-run reported v3→v9 without mutation; migrate reported a backup | Schema became v9 and the timestamped pre-v9 database remained present | Direct SQLite `user_version` and backup enumeration agreed |
| Claude lifecycle | Installed CLI completed dry-run/apply/check/self-test/uninstall | Only versioned Forecost-managed entries were added and removed in an isolated config | Self-test exercised the packaged fail-open launcher and all required lifecycle commands |
| Tamper classification | `verify --json` returned exit 1 and `rewritten` | First journal entry digest was changed in a disposable database copy | Sequence 1 was identified while receipt snapshots remained intact |
| Release evidence | Artifact metadata and wheel inspection passed | Checksums, SPDX SBOM, and in-toto/SLSA-shaped unsigned provenance were generated | Recorded subjects match independently computed artifact hashes |

## Residual risks and explicit boundaries

- The functional suite passes, but the first current-kernel mutation baseline
  killed 337 of 712 generated mutations; 274 survived, 95 timed out, and 6 had
  no test. This is test-precision debt, recorded in the evidence directory.
- A fresh vulnerability-database query was deliberately not made because this
  QA run prohibited external connections. Static security, secret, dependency
  consistency, and package-content checks ran locally; publication must refresh
  the advisory audit in CI.
- The offline installed environment inherited already-present third-party
  dependencies. The exact Python 3.12 base dependency snapshot is checked in,
  but clean optional-extra installs and the Python/OS matrix remain CI evidence.
- Live Claude/OpenAI/LangGraph/provider billing behavior and real-history import
  require sanitized founder-approved samples. Offline mappings do not imply live
  runtime completeness.
- Resource envelopes remain experimental, single-host controls and do not bound
  provider-side or distributed overrun.

## Final verdict

**GO WITH KNOWN RISK**

The 0.3.0 core is suitable for founder review and controlled local design-partner
trials. Publication remains held until the founder-controlled matrix,
vulnerability refresh, real-runtime validation, and public-claim review are
completed.
