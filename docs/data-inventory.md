# Forecost local data inventory

| Field family | Source | At-rest representation | Retention/use |
| --- | --- | --- | --- |
| Prompt, completion, tool payload, source code | Agent/runtime input | Current typed ledger/adapters reject these fields; current diagnostics use finite codes and keyed fingerprints. The exported legacy SDK still accepts arbitrary metadata into `costs.db`. | Current-ledger exclusion tests; quarantine/remove or constrain legacy before an end-to-end claim |
| Workspace path, session/run/source IDs | Adapter/hook input | Newly written or lazily migrated Claude cursor/path and error identities use installation-keyed HMACs; cursor state also retains keyed file-identity and complete-prefix rewrite checkpoints. Pre-hardening `ingest_state` rows may still contain raw cursor keys and prompt values until both usage and causal migrations run. Other canonical/legacy SHA-256 pseudonyms retain their documented linkability, and legacy project name/path storage remains raw. | Grouping/idempotency without disclosure from remediated cursor/log state; not anonymity, proof about an in-place upgrade, or a legacy-SDK guarantee |
| Trace/span IDs | Runtime/OTel input | W3C identifier when valid; otherwise pseudonym. Projection joins use a deterministic `span_key` derived from trace + span, never a bare span ID. | Causal graph only; v10 migration rebuilds from the journal and fails on ambiguous ownership |
| Span timing | Runtime/OTel input | Explicit `started_at`/`ended_at`, or a source-reported duration with its semantic and producer; occurrence/observation latency is retained separately and never used as duration | Complete explicit intervals support service/wait unions and elapsed envelope. Non-trivial critical path is withheld until scheduling dependencies are typed; only the one-span case is populated. |
| Token/tool/meter quantity | Runtime, gateway, transcript | Integer micros plus aggregation/finality | Receipt and reconciliation |
| Valuation/billing amount | List-rate engine, gateway, local export | Integer micros, explicit authority and tariff components | Receipt and reconciliation |
| Outcome mark | User/test/build/git fact | Enum status, reason-code pseudonym, confidence | Receipt evidence |
| Error diagnostics | Forecost internal failures | New `error.log` entries contain a finite component/code plus installation-keyed exception fingerprint, never arbitrary exception text. A pre-hardening free-text log is truncated only on the next diagnostic write; installing or opening the database does not rewrite it. | Debug by code/fingerprint correlation for remediated state; inventory or explicitly remove a legacy log before making the current at-rest claim |
| Durable queues and hook state | Usage callbacks, failed writes, settlement/lifecycle handlers | Recovery JSONL, gateway outbox, hook state, pending-settlement markers; bounded queued usage/settlement records; current append paths reject symlink targets. Successful recovery durably publishes a finite replay summary before removing the raw queue; failed publication retains it for idempotent retry. Preexisting files keep their original bytes until the relevant path drains, overwrites, or an operator deliberately removes them. | Treat each as an owned persistence surface; do not equate package/schema upgrade with sanitization; test crash, replay, privacy, purge, and same-path replacement |
| Cursor identity key | Forecost installation | Owner-only `installation-hmac.key` plus registered ID sidecar; accidental loss, corruption, or mismatch of one file fails when dependent keyed cursors are visible in the canonical home. Coordinated same-UID replacement of both matching files is not detectable. | Protect cursor/error identifiers; purge both with their dependent state; not a boundary against the same UID or custom ledgers the canonical-home check cannot see |
| SQLite operational files | Forecost journal/projections | `ledger.db`, WAL/SHM/journal sidecars, and timestamped schema backups. A backup is an exact logical pre-migration image and may retain raw pre-hardening cursor keys/values even after the live database is remediated. | Canonical connections use `synchronous=FULL`; migration uses a verified SQLite Backup API snapshot that includes committed WAL pages. Treat retained rollback images according to the oldest version they contain. |
| Legacy data | Retired tracker/forecaster and exported SDK compatibility | `costs.db` and legacy recovery artifacts; project names, paths, and arbitrary metadata may be raw | Remaining publication/privacy blocker; explicit migration does not make the source content-minimizing |
| Current integration configuration | Claude setup/plugin | Claude settings plus bounded Forecost hook sidecars; successful setup removes exact legacy `.forecost.bak` files. The source plugin launcher accepts only the exact owner-controlled plugin-data executable and runtime bootstrap is disabled. | Experimental/source-review only; no supported marketplace/PyPI install path yet |
| Proposed integration configuration | Codex universal plugin | Proposed manifest, skill, MCP config, and hook registration | Not shipped; add to the owned-state manifest if implemented |
| Current exported artifacts | User commands and package QA | Receipt v2 JSON/Markdown/text, local reports, SBOM/provenance | Explicit user-selected destination and retention; named profiles expose independent completeness/freshness/contradiction axes and unmet denominators |
| Proposed exported artifacts | Future product/CI | Sanitized HTML/SVG cards and assertion/proof bundles | Not shipped; require an explicit disclosure profile and never upload raw input by default |
| Policy material | Local operator input | Owner policy file and bounded policy decisions; interactive errors fail open, explicit CI mode may fail closed | Local process boundary only; repository policy is opt-in |
| Signing material | Proposed later surfaces | External signing identities or receipt signatures | Not a current assurance; local HMAC cursor key is not a receipt-signing key |

Forecost is local-only. The same-user threat boundary still applies: a user or
process that can alter the local database can alter local evidence; receipt
digests make malformed or modified snapshots detectable, not tamper-proof.

This inventory records the implemented current-ledger boundary and known
exceptions. It must not be used as evidence that the 0.3.0 checkout is
content-free end to end. See the
[2026-08-13 red team](research/2026-08-13-startup-grade-red-team-v2.md).

The current purge manifest covers known DB sidecars, schema backups, error,
recovery, hook/outbox, policy, ownership-marker, legacy DB, and installation-key
files under one validated `FORECOST_HOME`; it preserves and reports unknown
entries. It cannot discover user-configured ledger/outbox paths, exports,
integration state, or other files outside that root. A clean purge report is
therefore evidence only about its named root and manifest, never a machine-wide
deletion guarantee.

## In-place upgrade truth

The schema ladder preserves evidence; it is not a privacy rewrite. The current
upgrade path has four distinct states that must not be collapsed:

| Surface | What upgrades automatically | What can remain indefinitely |
| --- | --- | --- |
| Live Claude cursor rows | Each source migrates its rows when that source's current adapter path next polls. Usage and causal cursors migrate independently. | Raw transcript-path keys and raw prompt values when the corresponding poll has not run, cannot run, or rolls back on an identity collision. |
| `error.log` | The first successful current diagnostic write discards a noncanonical legacy log before appending the finite record. | Arbitrary historical free text when no later diagnostic write occurs. |
| Hook/outbox/recovery state | Current writers constrain new records; successful drains or overwrites can retire particular active files. | Historical records that are still pending, failed validation, were never revisited, or live in an archived/replayed file. |
| Schema backup | Nothing; exactness is the rollback contract. | Every logical byte present before migration, including legacy cursor identities. |

A privacy-sensitive upgrade therefore requires an operator-owned inventory of
the live database, every rollback backup, `error.log`, hook/outbox/recovery
state, configured paths outside `FORECOST_HOME`, integration backups, and
exports. Pending data must be drained or dispositioned deliberately; exact
rollback images must be retained as sensitive or deleted only after the owner
closes the rollback window. Forecost intentionally performs neither action
silently.

`forecost privacy verify --canary …` can prove whether one supplied canary is
present in readable files under one selected root. It cannot prove that unknown
historical free text is absent, classify every old record, inspect external
paths it was not given, or establish that a lazy cursor migration ran. Until a
supported state-audit/sanitization workflow and upgrade tests cover those
cases, an in-place upgraded home remains a release blocker for the end-to-end
content-minimizing claim.
