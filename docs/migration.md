# Migration and rollback guide

Forecost 0.3 introduces the canonical receipt ledger while retaining the v0.2
`costs.db` only as unsupported compatibility input. Do not point a migration
test at the only copy of real data.

## Safe sequence

1. Stop writers and record the installed Forecost version.
2. Copy the entire Forecost data root to owner-only backup storage.
3. Run the schema migration in dry-run mode against a copy.
4. Inspect the proposed schema version, row counts, rejected records, legacy
   labels, and backup destination.
5. Run the migration against the copy, then run `forecost verify`,
   `forecost privacy verify`, `forecost doctor --json`, and representative
   receipts.
6. Restore the copied backup into another temporary directory and prove the
   old version can read it before touching the original.
7. Only then repeat against the original data root.

## Compatibility law

Legacy floating postings and weak identities are preserved as legacy evidence.
Migration must convert money deterministically to integer micros, retain the
source value/provenance needed to audit rounding, and assign conservative
authority/finality. It must not manufacture graph parents, billed authority,
or complete source coverage.

## Rollback

There is no reverse schema migration. Rollback means stopping writers and
restoring the complete pre-migration backup. Never copy individual SQLite files
while a writer is active, and never mix a restored database with newer recovery
spools or hook state.

## Manual gate

Running this sequence on real user data is founder-owned work. Automated tests
use synthetic copies and deliberately cannot authorize an irreversible real
migration.
