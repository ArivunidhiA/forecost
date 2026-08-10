"""Offline, source-aware reconciliation imports and aggregate constraints."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import cast

from forecost.ledger.contracts import CausalIdentity, canonical_json, opaque_id
from forecost.ledger.evidence import append_observation, observation

_SOURCES = frozenset({"openai", "anthropic", "gateway", "otel"})


def _as_micros(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("billing amount must be numeric")
    try:
        decimal = Decimal(str(value))
    except Exception as error:
        raise ValueError("billing amount must be numeric") from error
    if not decimal.is_finite() or decimal < 0:
        raise ValueError("billing amount must be finite and non-negative")
    return int((decimal * Decimal("1000000")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _timestamp(value: object) -> datetime:
    if isinstance(value, int) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("billing timestamp is invalid") from error
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc)
    raise ValueError("billing record needs a timezone-aware timestamp")


def _records_from_json(value: object) -> list[Mapping[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    if not isinstance(value, Mapping):
        raise ValueError("billing JSON must be an object or array")
    data = value.get("data", value.get("results", value))
    if isinstance(data, list):
        return _flatten_records(data)
    return [value]


def _flatten_records(values: list[object]) -> list[Mapping[str, object]]:
    records: list[Mapping[str, object]] = []
    for item in values:
        if isinstance(item, Mapping):
            records.extend(_flatten_record(item))
    return records


def _flatten_record(item: Mapping[str, object]) -> list[Mapping[str, object]]:
    nested = item.get("results")
    if not isinstance(nested, list):
        return [item]
    return [{**item, **child} for child in nested if isinstance(child, Mapping)]


def _load_records(path: Path) -> list[Mapping[str, object]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    with path.open(encoding="utf-8") as handle:
        return _records_from_json(json.load(handle))


def _record_amount(record: Mapping[str, object]) -> int:
    if "amount_micros" in record:
        value = record["amount_micros"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("amount_micros must be a non-negative integer")
        return value
    amount = record.get("amount")
    if isinstance(amount, Mapping) and "value" in amount:
        return _as_micros(amount["value"])
    for key in ("cost_usd", "amount", "cost"):
        if key in record:
            return _as_micros(record[key])
    raise ValueError("billing record needs amount_micros, amount, cost, or cost_usd")


def _record_timestamp(record: Mapping[str, object]) -> datetime:
    for key in ("timestamp", "starting_at", "start_time", "time", "date"):
        if key in record:
            return _timestamp(record[key])
    raise ValueError("billing record needs timestamp, starting_at, start_time, time, or date")


def _stable_file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _existing_import_root(conn: sqlite3.Connection, run_id: str | None) -> sqlite3.Row | None:
    if run_id is None:
        return None
    return cast(
        sqlite3.Row | None,
        conn.execute(
            "SELECT * FROM causal_spans WHERE run_id = ? ORDER BY source_order LIMIT 1",
            (opaque_id("run", run_id),),
        ).fetchone(),
    )


def _new_import_identity(digest: str, source: str) -> CausalIdentity:
    return CausalIdentity(
        conversation_id=f"import-conversation-{digest}",
        trace_id=digest[:32],
        run_id=f"import-{source}-{digest}",
        span_id=digest[32:48],
        source_sequence=0,
        idempotency_key=f"import-root-{digest}",
    )


def _stored_import_identity(existing: sqlite3.Row, digest: str) -> CausalIdentity:
    return CausalIdentity(
        conversation_id=existing["conversation_id"],
        trace_id=existing["trace_id"],
        run_id=existing["run_id"],
        span_id=existing["span_id"],
        source_sequence=0,
        idempotency_key=f"import-root-{digest}",
    )


def _import_root(
    conn: sqlite3.Connection,
    source: str,
    digest: str,
    records: list[Mapping[str, object]],
    run_id: str | None,
) -> CausalIdentity:
    existing = _existing_import_root(conn, run_id)
    if existing is not None:
        return _stored_import_identity(existing, digest)
    root = _new_import_identity(digest, source)
    occurred_at = _record_timestamp(records[0])
    append_observation(
        conn,
        observation(
            producer=f"billing-{source}",
            event_kind="span",
            causal=root,
            payload={
                "operation_kind": "custom",
                "lifecycle": "completed",
                "branch_id": "billing",
            },
            occurred_at=occurred_at,
            observed_at=occurred_at,
        ),
    )
    return root


def _line_item(record: Mapping[str, object]) -> str:
    value = record.get("line_item", record.get("model", "model_inference"))
    return value if isinstance(value, str) else "model_inference"


def _account_scope(record: Mapping[str, object]) -> str | None:
    value = record.get("project_id", record.get("workspace_id", record.get("account_id")))
    if value is None or isinstance(value, str):
        return value
    return str(value)


def _fact_id(record: Mapping[str, object]) -> str | None:
    value = record.get("fact_id")
    if value is not None and not isinstance(value, str):
        raise ValueError("fact_id must be a string when supplied")
    return value


def _append_import_record(
    conn: sqlite3.Connection,
    root: CausalIdentity,
    source: str,
    digest: str,
    index: int,
    record: Mapping[str, object],
) -> bool:
    occurred_at = _record_timestamp(record)
    causal = replace(root, source_sequence=index, idempotency_key=f"import-{digest}-{index}")
    return append_observation(
        conn,
        observation(
            producer=f"billing-{source}",
            event_kind="charge",
            causal=causal,
            payload={
                "fact_id": _fact_id(record),
                "amount_micros": _record_amount(record),
                "currency": "USD",
                "authority": "billed",
                "line_item": _line_item(record),
                "tariff": {},
                "account_scope": _account_scope(record),
                "finality": "final",
            },
            occurred_at=occurred_at,
            observed_at=occurred_at,
        ),
    )


def import_bill_file(
    conn: sqlite3.Connection,
    path: Path,
    source: str,
    *,
    run_id: str | None = None,
) -> tuple[str, int]:
    """Import representative provider/gateway/OTel exports without HTTP or credentials.

    Any unsupported columns are ignored and never persisted.  The accepted
    fields are deliberately small: timestamp, amount, optional line item, and
    optional account scope.  An imported aggregate without a caller-provided
    run becomes its own evidence-only run rather than being falsely matched to
    local callbacks.
    """
    if source not in _SOURCES:
        raise ValueError(f"unsupported import source: {source}")
    if not path.is_file():
        raise ValueError("billing file does not exist")
    digest = _stable_file_digest(path)
    records = _load_records(path)
    if not records:
        raise ValueError("billing file contains no records")
    root = _import_root(conn, source, digest, records, run_id)
    imported = sum(
        _append_import_record(conn, root, source, digest, index, record)
        for index, record in enumerate(records, start=1)
    )
    return root.normalized().run_id, imported


def _reconciliation_queries() -> tuple[str, str]:
    cte = """
        WITH active AS (
            SELECT c.* FROM charges c
            WHERE NOT EXISTS (
                SELECT 1 FROM charges newer
                WHERE newer.supersedes_charge_id = c.charge_id
            )
            AND (? IS NULL OR EXISTS (
                SELECT 1 FROM causal_spans s
                WHERE s.span_id = c.span_id AND s.run_id = ?
            ))
        ),
        ranked_local AS (
            SELECT active.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY COALESCE(fact_id, span_id), currency, line_item
                       ORDER BY CASE authority
                           WHEN 'provider_estimate' THEN 0
                           WHEN 'gateway_estimate' THEN 1
                           WHEN 'list_rate' THEN 2
                           ELSE 99 END,
                           observed_at, charge_id
                   ) AS authority_rank
            FROM active
            WHERE authority IN ('provider_estimate', 'gateway_estimate', 'list_rate')
        ),
        local AS (SELECT * FROM ranked_local WHERE authority_rank = 1),
        provider AS (SELECT * FROM active WHERE authority = 'billed'),
        local_keys AS (
            SELECT DISTINCT fact_id, currency, line_item FROM local WHERE fact_id IS NOT NULL
        ),
        provider_keys AS (
            SELECT DISTINCT fact_id, currency, line_item FROM provider WHERE fact_id IS NOT NULL
        )
    """
    stats_sql = (
        cte  # noqa: S608  # nosec B608
        + """
        SELECT
            (SELECT COUNT(*) FROM local) AS local_count,
            (SELECT COUNT(*) FROM provider) AS provider_count,
            COALESCE((SELECT SUM(amount_micros) FROM local), 0) AS local_total,
            COALESCE((SELECT SUM(amount_micros) FROM provider), 0) AS provider_total,
            (SELECT COUNT(*) FROM local_keys l
             JOIN provider_keys p USING(fact_id, currency, line_item)) AS exact_match_count,
            (SELECT COUNT(*) FROM local l
             JOIN provider_keys p USING(fact_id, currency, line_item)) AS matched_local_count,
            (SELECT COUNT(*) FROM provider p
             JOIN local_keys l USING(fact_id, currency, line_item)) AS matched_provider_count,
            COALESCE((SELECT MIN(finality = 'final') FROM (
                SELECT finality FROM local UNION ALL SELECT finality FROM provider
            )), 0) AS all_inputs_final,
            (SELECT MIN(occurred_at) FROM (
                SELECT occurred_at FROM local UNION ALL SELECT occurred_at FROM provider
            )) AS window_start,
            (SELECT MAX(occurred_at) FROM (
                SELECT occurred_at FROM local UNION ALL SELECT occurred_at FROM provider
            )) AS window_end
        """
    )
    evidence_sql = (
        cte  # noqa: S608  # nosec B608
        + """
        SELECT l.observation_id, 'local' AS source_role,
               CASE WHEN p.fact_id IS NOT NULL
                    THEN 'exact_identity' ELSE 'aggregate_constraint' END AS match_state
        FROM local l
        LEFT JOIN provider_keys p USING(fact_id, currency, line_item)
        UNION ALL
        SELECT p.observation_id, 'provider_bill' AS source_role,
               CASE WHEN l.fact_id IS NOT NULL
                    THEN 'exact_identity' ELSE 'aggregate_constraint' END AS match_state
        FROM provider p
        LEFT JOIN local_keys l USING(fact_id, currency, line_item)
        ORDER BY source_role, observation_id
        """
    )
    return stats_sql, evidence_sql


@dataclass(frozen=True)
class _ReconciliationStats:
    local_count: int
    provider_count: int
    local_total: int
    provider_total: int
    exact_match_count: int
    unmatched_local_count: int
    unmatched_provider_count: int
    window_start: str | None
    window_end: str | None
    all_inputs_final: bool

    @property
    def residual(self) -> int:
        return self.provider_total - self.local_total

    @property
    def observed(self) -> int:
        return int(self.local_count > 0) + int(self.provider_count > 0)


def _load_reconciliation_stats(
    conn: sqlite3.Connection, stats_sql: str, params: tuple[object, ...]
) -> _ReconciliationStats:
    row = conn.execute(stats_sql, params).fetchone()
    local_count = int(row["local_count"])
    provider_count = int(row["provider_count"])
    return _ReconciliationStats(
        local_count=local_count,
        provider_count=provider_count,
        local_total=int(row["local_total"]),
        provider_total=int(row["provider_total"]),
        exact_match_count=int(row["exact_match_count"]),
        unmatched_local_count=local_count - int(row["matched_local_count"]),
        unmatched_provider_count=provider_count - int(row["matched_provider_count"]),
        window_start=row["window_start"],
        window_end=row["window_end"],
        all_inputs_final=bool(row["all_inputs_final"]),
    )


def _reconciliation_state(stats: _ReconciliationStats, tolerance_micros: int) -> tuple[str, str]:
    if stats.observed == 0:
        return "unknown", "unknown"
    if stats.observed < 2:
        return "incomplete", "provisional"
    state = "reconciled" if abs(stats.residual) <= tolerance_micros else "discrepant"
    finality = "final" if stats.all_inputs_final else "provisional"
    return state, finality


def _evidence_digest(
    conn: sqlite3.Connection, evidence_sql: str, params: tuple[object, ...]
) -> str:
    evidence_hasher = hashlib.sha256()
    for row in conn.execute(evidence_sql, params):
        observation_id = str(row["observation_id"])
        evidence_hasher.update(observation_id.encode("ascii"))
        evidence_hasher.update(b"\0")
    return evidence_hasher.hexdigest()


def _reconciliation_material(
    normalized_run: str | None,
    stats: _ReconciliationStats,
    tolerance_micros: int,
    state: str,
    evidence_digest: str,
) -> dict[str, object]:
    return {
        "run_id": normalized_run,
        "local_total": stats.local_total,
        "provider_total": stats.provider_total,
        "residual": stats.residual,
        "tolerance": tolerance_micros,
        "state": state,
        "local_count": stats.local_count,
        "provider_count": stats.provider_count,
        "exact_match_count": stats.exact_match_count,
        "unmatched_local_count": stats.unmatched_local_count,
        "unmatched_provider_count": stats.unmatched_provider_count,
        "expected": 2,
        "observed": stats.observed,
        "evidence_digest": evidence_digest,
    }


def _prior_batch(conn: sqlite3.Connection, normalized_run: str | None) -> sqlite3.Row | None:
    prior_query = (
        "SELECT batch_id FROM reconciliation_batches WHERE run_id = ? "
        "ORDER BY created_at DESC, batch_id DESC LIMIT 1"
        if normalized_run is not None
        else "SELECT batch_id FROM reconciliation_batches WHERE run_id IS NULL "
        "ORDER BY created_at DESC, batch_id DESC LIMIT 1"
    )
    prior_params = (normalized_run,) if normalized_run is not None else ()
    return cast(sqlite3.Row | None, conn.execute(prior_query, prior_params).fetchone())


def _public_result(
    material: dict[str, object],
    batch_id: str,
    finality: str,
    supersedes_batch_id: str | None,
    *,
    reused: bool,
) -> dict[str, object]:
    return {
        **{key: value for key, value in material.items() if key != "evidence_digest"},
        "batch_id": batch_id,
        "finality": finality,
        "supersedes_batch_id": supersedes_batch_id,
        "reused": reused,
    }


def _persist_reconciliation(
    conn: sqlite3.Connection,
    normalized_run: str | None,
    stats: _ReconciliationStats,
    tolerance_micros: int,
    state: str,
    finality: str,
    batch_id: str,
    supersedes_batch_id: str | None,
    evidence_sql: str,
    params: tuple[object, ...],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    window_start = stats.window_start or now
    window_end = stats.window_end or now
    conn.execute(
        """
        INSERT INTO reconciliation_batches(
            batch_id, schema_version, run_id, source_set_json, account_scope, dimensions_json,
            window_start, window_end, watermarks_json, expected_count, observed_count,
            unmatched_local_count, unmatched_provider_count, local_amount_micros,
            provider_amount_micros, residual_micros, tolerance_micros, finality, state, created_at,
            supersedes_batch_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            batch_id,
            1,
            normalized_run,
            canonical_json(
                {"local": stats.local_count > 0, "provider_bill": stats.provider_count > 0}
            ),
            None,
            "{}",
            window_start,
            window_end,
            canonical_json({"as_of": now}),
            2,
            stats.observed,
            stats.unmatched_local_count,
            stats.unmatched_provider_count,
            stats.local_total,
            stats.provider_total,
            stats.residual,
            tolerance_micros,
            finality,
            state,
            now,
            supersedes_batch_id,
        ),
    )
    conn.execute("DELETE FROM reconciliation_evidence WHERE batch_id = ?", (batch_id,))
    conn.executemany(
        "INSERT INTO reconciliation_evidence("
        "batch_id, observation_id, source_role, match_state) VALUES (?,?,?,?)",
        (
            (batch_id, row["observation_id"], row["source_role"], row["match_state"])
            for row in conn.execute(evidence_sql, params)
        ),
    )
    conn.commit()


def reconcile_run(
    conn: sqlite3.Connection,
    run_id: str | None,
    *,
    tolerance_micros: int = 1_000,
) -> dict[str, object]:
    """Compare local valuations and provider bills without forced matching.

    Canonical authority selection and aggregate constraints execute in SQLite.
    Python receives one statistics row and streams evidence identifiers, so the
    memory footprint does not grow with the number of charge rows.
    """
    if tolerance_micros < 0:
        raise ValueError("tolerance_micros must be non-negative")
    normalized_run = opaque_id("run", run_id) if run_id is not None else None
    params: tuple[object, ...] = (normalized_run, normalized_run)
    stats_sql, evidence_sql = _reconciliation_queries()
    stats = _load_reconciliation_stats(conn, stats_sql, params)
    state, finality = _reconciliation_state(stats, tolerance_micros)
    material = _reconciliation_material(
        normalized_run,
        stats,
        tolerance_micros,
        state,
        _evidence_digest(conn, evidence_sql, params),
    )
    batch_id = opaque_id("reconciliation", canonical_json(material))
    prior = _prior_batch(conn, normalized_run)
    if prior is not None and prior["batch_id"] == batch_id:
        return _public_result(material, batch_id, finality, None, reused=True)
    supersedes_batch_id = prior["batch_id"] if prior is not None else None
    _persist_reconciliation(
        conn,
        normalized_run,
        stats,
        tolerance_micros,
        state,
        finality,
        batch_id,
        supersedes_batch_id,
        evidence_sql,
        params,
    )
    return _public_result(material, batch_id, finality, supersedes_batch_id, reused=False)
