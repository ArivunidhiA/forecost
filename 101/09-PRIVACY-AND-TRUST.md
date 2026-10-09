# Privacy, security, and trust

## The privacy contract and its remaining boundary

The current ledger contract uses a field allowlist to exclude content-shaped
fields from canonical evidence: ingestion contracts accept bounded causal/
economic metadata. The worktree also repairs the red-team findings in current
Claude cursor, diagnostic, scanner, recovery, append, and purge paths.

| May persist | Must not persist |
| --- | --- |
| Pseudonymous workspace/session/run identity | Raw workspace paths |
| Valid or pseudonymous trace/span identity | Prompts and completions |
| Token/call quantities | Tool arguments and output |
| Models and bounded lifecycle codes | Source code or file contents |
| Timestamps and finality | Credentials and secrets |
| Authority-labelled valuations | Arbitrary baggage/tracestate |
| Bounded outcome codes | Unbounded external error strings |
| Internal recovery diagnostics | Private transcript bodies |

The test `tests/test_privacy_canary.py` plants a sentinel in synthetic prompt,
tool-input, and tool-output positions and fails if it reaches Forecost-owned
state. `forecost privacy verify` now streams regular files in the selected root
without the former size skip, detects canaries across chunk boundaries, reports
bytes/files scanned, and returns an inconclusive failure if a path is unreadable,
symlinked, or non-regular and therefore skipped. This is a sentinel check, not a
proof that every possible secret is absent.

Current-path protections:

- Claude cursor identities and diagnostic fingerprints use an owner-only
  installation HMAC key rather than raw paths or arbitrary exception text.
- A cursor binds the transcript's file identity and a keyed complete-prefix
  checkpoint; detected same-path replacement or prefix rewriting forces safe
  re-reading.
- The key and its registered ID are private and atomically created. Accidental
  loss, corruption, or mismatch of one file fails when dependent keyed cursors
  are visible in the canonical home. A same-UID process can replace both files
  consistently, which this local mechanism cannot detect.
- Successful recovery durably publishes a finite replay summary before deleting
  the raw queue; if summary publication fails, the raw queue is retained for
  idempotent retry. Hook/outbox append paths reject symlink targets.
- Purge's manifest includes current DB sidecars, recovery/hook/outbox files,
  identity keys, schema backups, and crash temps under the selected home.

Remaining release blockers:

- The backward-compatible SDK is still exported, and legacy project/tracker
  paths may write arbitrary raw project name, path, and metadata to `costs.db`.
- User-selected ledger/outbox paths, explicit exports, and integration state
  outside `FORECOST_HOME` cannot be exhaustively discovered by privacy scan or
  purge.
- An owner-readable local HMAC key is not protection from same-UID code.

Therefore say **content-minimizing within documented current-ledger and
owned-home paths**, not content-free end to end. The remaining release gates are
tracked in the
[master checklist](../docs/research/2026-08-13-master-product-launch-checklist.md).

## Threat model

Forecost treats runtime data, offline imports, hook input, environment
variables, and repository-local configuration as untrusted. Important threats
include:

- accidental content persistence;
- raw path or identifier disclosure;
- duplicate replay and double-counting;
- partial writes and cursor loss;
- stale evidence at a policy decision;
- authority inflation, such as calling list rate “actual cost”;
- self-attested comparison manifests being mistaken for authenticated
  assignment, evaluator, outcome, or provider evidence;
- cloned repositories imposing policy on the user;
- destructive cleanup outside Forecost-owned paths.

## What local-first does and does not mean

Local-first means there is no required Forecost account, hosted tier, or current
network-backed ingestion service. It reduces data sharing; it does not make the
database harmless. Causal timing and pseudonymous grouping can reveal work
patterns, so the data root is private and should be owner-only.

The same operating-system user can alter their own database. Integrity checks
detect certain mutation classes but cannot provide signed, externally attested
truth.

That boundary also applies to comparison. Manifest and result SHA-256 digests
bind local serialization; they do not sign or authenticate the declared task,
configuration, assignment, evaluator, or source. Stable comparison IDs may also
reveal relationships between otherwise pseudonymous runs.

Comparison does detect a narrower local inconsistency class. It copies one
WAL-consistent state into memory, verifies the journal chain, and
deterministically rebuilds/hash-checks journal-derived projections before using
them. A broken chain, projection-only edit, or recognized rebuild failure makes
the evidence invalid. This remains a same-database check, not a defense against
a same-UID actor replacing the journal, anchor, projections, and manifests
consistently. Reconciliation batches are outside that derived inventory, so any
such row causes comparison v1 to abstain rather than call it verified.

The optional MCP and comparison CLI are read-only at the Forecost data-model
level: they do not create/migrate schema or insert, update, or delete ledger
rows. SQLite still may create or update `-wal`/`-shm` coordination sidecars when
an existing WAL database is opened with `mode=ro`. Forecost does not use
`immutable=1`, because that can ignore committed WAL pages and return stale
evidence. Do not interpret the read-only annotation as a zero-filesystem-write
guarantee.

## Policy trust

The governing policy file is normally `~/.forecost/policy.toml`. A repository's
`.forecost.toml` is ignored for enforcement unless the user deliberately sets:

```bash
export FORECOST_TRUST_PROJECT_POLICY=1
```

This prevents a cloned repository from silently imposing a deny rule on the
user's agent session.

## Failure modes for controls

Interactive Claude hooks and gateway callbacks are designed so an unavailable,
stale, or broken Forecost does not take down the host. A healthy local hook can
return `ask` or `deny` within its observed process boundary. A protected CI
policy may explicitly select `mode = "ci"` with
`on_internal_error = "deny"`; the LiteLLM boundary can also be constructed with
`ci_fail_closed=True`, which remains closed if its policy is unavailable or
corrupt. Interactive policy cannot silently choose that failure mode.

Neither failure mode changes these limits:

- work already admitted by a provider may continue;
- another machine or bypass path may be invisible;
- maximum external overrun is not bounded;
- no provider-side or distributed guarantee is claimed.

Use `OBSERVED`, `NOT OBSERVED`, and `CONTAINED` only as the CLI defines them and
only within the stated local boundary.

## Safe issue reporting

Never attach a real transcript, ledger database, policy file, API key, prompt,
tool payload, or absolute workspace path to an issue. Build a synthetic fixture
that reproduces the behavior. Report vulnerabilities through a private GitHub
security advisory or the maintainer's private channel described in
[`SECURITY.md`](../SECURITY.md).

## Deletion and migration safety

`forecost purge` is intentionally allow-listed and ownership-aware. It removes
known current and legacy files under one validated home, handles known
hook/outbox directories entry-by-entry, and preserves/reports unknown entries.
It is not a machine-wide deletion mechanism and cannot discover custom state
paths outside that home. Inspect its preserved-entry report, help, and target
before confirming. Custom data roots must be absolute, owned, and safe; broad
roots, workspace roots, symlinks, and unowned targets are rejected.

Schema migration is forward-only. The command creates a verified SQLite Backup
API snapshot (including committed WAL pages) before applying changes and
removes a partial/invalid snapshot. Still test on a copy, stop writers, verify
restore in your environment, and never splice one SQLite file into operational
files from another point in time. See
[`docs/migration.md`](../docs/migration.md).
