"""Offline, source-aware reconciliation imports and aggregate constraints."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

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
        records: list[Mapping[str, object]] = []
        for item in data:
            if not isinstance(item, Mapping):
                continue
            nested = item.get("results")
            if isinstance(nested, list):
                for child in nested:
                    if isinstance(child, Mapping):
                        records.append({**item, **child})
            else:
                records.append(item)
        return records
    return [value]


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
    raw_run = run_id or f"import-{source}-{digest}"
    existing = (
        conn.execute(
            "SELECT * FROM causal_spans WHERE run_id = ? ORDER BY source_order LIMIT 1",
            (opaque_id("run", raw_run),),
        ).fetchone()
        if run_id is not None
        else None
    )
    if existing is None:
        root = CausalIdentity(
            conversation_id=f"import-conversation-{digest}",
            trace_id=digest[:32],
            run_id=raw_run,
            span_id=digest[32:48],
            source_sequence=0,
            idempotency_key=f"import-root-{digest}",
        )
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
                occurred_at=_record_timestamp(records[0]),
                observed_at=_record_timestamp(records[0]),
            ),
        )
    else:
        root = CausalIdentity(
            conversation_id=existing["conversation_id"],
            trace_id=existing["trace_id"],
            run_id=existing["run_id"],
            span_id=existing["span_id"],
            source_sequence=0,
            idempotency_key=f"import-root-{digest}",
        )
    imported = 0
    for index, record in enumerate(records, start=1):
        amount = _record_amount(record)
        occurred_at = _record_timestamp(record)
        line_item = record.get("line_item", record.get("model", "model_inference"))
        if not isinstance(line_item, str):
            line_item = "model_inference"
        account_scope = record.get(
            "project_id", record.get("workspace_id", record.get("account_id"))
        )
        if account_scope is not None and not isinstance(account_scope, str):
            account_scope = str(account_scope)
        fact_id = record.get("fact_id")
        if fact_id is not None and not isinstance(fact_id, str):
            raise ValueError("fact_id must be a string when supplied")
        causal = replace(
            root,
            source_sequence=index,
            idempotency_key=f"import-{digest}-{index}",
        )
        if append_observation(
            conn,
            observation(
                producer=f"billing-{source}",
                event_kind="charge",
                causal=causal,
                payload={
                    "fact_id": fact_id,
                    "amount_micros": amount,
                    "currency": "USD",
                    "authority": "billed",
                    "line_item": line_item,
                    "tariff": {},
                    "account_scope": account_scope,
                    "finality": "final",
                },
                occurred_at=occurred_at,
                observed_at=occurred_at,
            ),
        ):
            imported += 1
    return root.normalized().run_id, imported


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
        cte  # noqa: S608 - composed exclusively from static SQL literals
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
    stats = conn.execute(stats_sql, params).fetchone()
    local_count = int(stats["local_count"])
    provider_count = int(stats["provider_count"])
    local_total = int(stats["local_total"])
    provider_total = int(stats["provider_total"])
    exact_match_count = int(stats["exact_match_count"])
    unmatched_local_count = local_count - int(stats["matched_local_count"])
    unmatched_provider_count = provider_count - int(stats["matched_provider_count"])
    residual = provider_total - local_total
    expected = 2
    observed = int(local_count > 0) + int(provider_count > 0)
    all_inputs_final = bool(stats["all_inputs_final"])
    if observed == 0:
        state, finality = "unknown", "unknown"
    elif observed < expected:
        state, finality = "incomplete", "provisional"
    elif abs(residual) <= tolerance_micros:
        state = "reconciled"
        finality = "final" if all_inputs_final else "provisional"
    else:
        state = "discrepant"
        finality = "final" if all_inputs_final else "provisional"
    evidence_hasher = hashlib.sha256()
    evidence_sql = (
        cte  # noqa: S608 - composed exclusively from static SQL literals
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
    for row in conn.execute(evidence_sql, params):
        observation_id = str(row["observation_id"])
        evidence_hasher.update(observation_id.encode("ascii"))
        evidence_hasher.update(b"\0")
    material = {
        "run_id": normalized_run,
        "local_total": local_total,
        "provider_total": provider_total,
        "residual": residual,
        "tolerance": tolerance_micros,
        "state": state,
        "local_count": local_count,
        "provider_count": provider_count,
        "exact_match_count": exact_match_count,
        "unmatched_local_count": unmatched_local_count,
        "unmatched_provider_count": unmatched_provider_count,
        "expected": expected,
        "observed": observed,
        "evidence_digest": evidence_hasher.hexdigest(),
    }
    batch_id = opaque_id("reconciliation", canonical_json(material))
    prior_query = (
        "SELECT batch_id FROM reconciliation_batches WHERE run_id = ? "
        "ORDER BY created_at DESC, batch_id DESC LIMIT 1"
        if normalized_run is not None
        else "SELECT batch_id FROM reconciliation_batches WHERE run_id IS NULL "
        "ORDER BY created_at DESC, batch_id DESC LIMIT 1"
    )
    prior_params = (normalized_run,) if normalized_run is not None else ()
    prior = conn.execute(prior_query, prior_params).fetchone()
    if prior is not None and prior["batch_id"] == batch_id:
        return {
            **{key: value for key, value in material.items() if key != "evidence_digest"},
            "batch_id": batch_id,
            "finality": finality,
            "supersedes_batch_id": None,
            "reused": True,
        }
    supersedes_batch_id = prior["batch_id"] if prior is not None else None
    now = datetime.now(timezone.utc).isoformat()
    window_start = stats["window_start"] or now
    window_end = stats["window_end"] or now
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
            canonical_json({"local": local_count > 0, "provider_bill": provider_count > 0}),
            None,
            "{}",
            window_start,
            window_end,
            canonical_json({"as_of": now}),
            expected,
            observed,
            unmatched_local_count,
            unmatched_provider_count,
            local_total,
            provider_total,
            residual,
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
    return {
        **{key: value for key, value in material.items() if key != "evidence_digest"},
        "batch_id": batch_id,
        "finality": finality,
        "supersedes_batch_id": supersedes_batch_id,
        "reused": False,
    }
