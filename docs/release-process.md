# Offline-first release process

Publication is intentionally the last and only external step.

> **2026-08-13 hold:** `docs/status.md` records unresolved P0 defects. A
> historical `GO WITH KNOWN RISK` verdict and founder acceptance are not enough
> while that hold remains. The master product/launch checklist and a new
> independent audit must explicitly clear every P0 before this process can
> publish.

## Build and verify

1. Start from a clean, reviewed commit and an empty `dist/` directory.
2. Run the release validator, formatting, lint, type, complexity, dead-code,
   security, dependency, secret, unit, property, conformance, failure, and
   performance gates.
3. Build wheel and sdist with a fixed `SOURCE_DATE_EPOCH`.
4. Inspect wheel contents and metadata; install the base artifact and each extra
   into empty temporary environments on all locally available supported Python
   versions.
5. Run the journeys in `golden-journeys.md` through the installed entry points,
   with external networking blocked and isolated data/config roots.
6. Generate local release evidence:

   ```bash
   SOURCE_DATE_EPOCH=... python scripts/build_release_evidence.py \
     --dist dist --output dist/evidence --source-root .
   ```

7. Freeze the initial `/qa` findings, repair every autonomous blocker, rerun
   from clean state, and issue exactly one verdict.

## Evidence bundle

- artifact SHA-256 checksums;
- SPDX 2.3 SBOM derived from the built artifact metadata;
- unsigned local in-toto/SLSA-shaped provenance identifying source commit,
  dirty state, builder, timestamp, and artifact subjects;
- test/type/lint/security/performance logs;
- installed-artifact journey evidence and final QA report.

The local provenance is inspectable build metadata, not a cryptographic
attestation. Signing keys, transparency logs, PyPI trusted publishing, release
tags, GitHub releases, marketplace publication, and unrelated-machine checks
remain founder-controlled external actions.

## Abort conditions

Abort for an active status/release hold, dirty or mismatched source commit, version disagreement, untracked
artifact input, failed base-wheel entry point, external network use, content
leak, integrity/conservation failure, unsupported claim, or a QA verdict other
than a new P0-clearing `GO` explicitly accepted by the founder.
