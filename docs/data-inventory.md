# Forecost local data inventory

| Field family | Source | At-rest representation | Retention/use |
| --- | --- | --- | --- |
| Prompt, completion, tool payload, source code | Agent/runtime input | Rejected; never persisted | None |
| Workspace path, session/run/source IDs | Adapter/hook input | Stable irreversible pseudonym | Local grouping/idempotency only |
| Trace/span IDs | Runtime/OTel input | W3C identifier when valid; otherwise pseudonym | Causal graph only |
| Token/tool/meter quantity | Runtime, gateway, transcript | Integer micros plus aggregation/finality | Receipt and reconciliation |
| Valuation/billing amount | List-rate engine, gateway, local export | Integer micros, explicit authority and tariff components | Receipt and reconciliation |
| Outcome mark | User/test/build/git fact | Enum status, reason-code pseudonym, confidence | Receipt evidence |
| Error/recovery diagnostics | Forecost internal failures | Bounded operational message; no source payload | Local recovery/doctor |

Forecost is local-only. The same-user threat boundary still applies: a user or
process that can alter the local database can alter local evidence; receipt
digests make malformed or modified snapshots detectable, not tamper-proof.
