# Migration and rollback guide

Forecost 0.3 introduces the canonical receipt ledger while retaining the v0.2
`costs.db` only as unsupported compatibility input. Do not point a migration
test at the only copy of real data.

## Safe sequence

1. Stop incompatible writers and record the installed Forecost version.
2. Copy non-SQLite owned state to owner-only backup storage. For `ledger.db`,
   use `forecost ledger migrate-schema`: it creates and integrity-checks a
   transactionally consistent SQLite Backup API snapshot, including committed
   WAL pages, before applying a schema change.
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
restoring the complete pre-migration backup. The migration `.bak` is a
standalone SQLite image; never combine it with WAL/SHM sidecars from another
point in time. Do not mix a restored database with newer recovery spools or
hook state.

The canonical ledger uses WAL plus `synchronous=FULL`. This establishes the
local SQLite commit boundary; it is not remote replication, protection from a
lying storage device, or same-user tamper resistance. See
[ADR 0008](adr/0008-sqlite-durability.md) for the exact boundary.

## Manual gate

Running this sequence on real user data is founder-owned work. Automated tests
use synthetic copies and deliberately cannot authorize an irreversible real
migration.
