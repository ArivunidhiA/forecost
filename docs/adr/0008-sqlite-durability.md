# ADR 0008: Canonical ledger commits and migrations are durability boundaries

## Decision

The canonical `ledger.db` runs in WAL mode with `PRAGMA synchronous=FULL`.
A successful synchronous ledger commit therefore waits for SQLite's FULL
durability boundary. This is stronger than the previous `NORMAL` setting,
which allowed a committed WAL transaction to be lost after power failure.

Schema migration never copies a live SQLite main file. Before migration,
Forecost uses SQLite's Backup API to create a standalone snapshot that includes
committed pages still resident in WAL. It runs `PRAGMA integrity_check` against
the snapshot before changing the source and against the migrated ledger before
reporting success. A failed partial snapshot is removed; a valid pre-migration
snapshot is retained if the later migration fails.

## Consequences and boundary

- The backup is a consistent SQLite database, so restore uses the single backup
  image rather than mixing a main file with WAL/SHM sidecars.
- Tests cover restore, injected backup failure cleanup, and committed concurrent
  WAL pages.
- `FULL` and successful integrity checks do not protect against a storage device
  that lies about `fsync`, catastrophic device loss, or a process with the same
  user's privileges deliberately replacing the database and backup.
- Callers must still stop incompatible old binaries and coordinate recovery
  spools or integration state during a real rollback.
