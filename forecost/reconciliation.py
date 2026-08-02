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
_LOCAL_AUTHORITIES = frozenset({"list_rate", "gateway_estimate", "provider_estimate"})
_LOCAL_AUTHORITY_ORDER = {"provider_estimate": 0, "gateway_estimate": 1, "list_rate": 2}


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
    """Compare local valuations and imported provider bills without forced matching."""
    if tolerance_micros < 0:
        raise ValueError("tolerance_micros must be non-negative")
    where = ""
    params: list[object] = []
    if run_id is not None:
        where = "JOIN causal_spans s ON s.span_id = c.span_id WHERE s.run_id = ?"
        params.append(opaque_id("run", run_id))
    rows = conn.execute(f"SELECT c.* FROM charges c {where}", params).fetchall()  # noqa: S608
    local_candidates = [row for row in rows if row["authority"] in _LOCAL_AUTHORITIES]
    grouped_local: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
    for row in local_candidates:
        key = (row["fact_id"] or row["span_id"], row["currency"], row["line_item"])
        grouped_local.setdefault(key, []).append(row)
    local = [
        sorted(
            candidates,
            key=lambda row: (
                _LOCAL_AUTHORITY_ORDER.get(row["authority"], 99),
                row["observed_at"],
                row["charge_id"],
            ),
        )[0]
        for candidates in grouped_local.values()
    ]
    provider = [row for row in rows if row["authority"] == "billed"]
    local_total = sum(int(row["amount_micros"]) for row in local)
    provider_total = sum(int(row["amount_micros"]) for row in provider)
    residual = provider_total - local_total
    expected = 2
    observed = int(bool(local)) + int(bool(provider))
    if observed == 0:
        state, finality = "unknown", "unknown"
    elif observed < expected:
        state, finality = "incomplete", "provisional"
    elif abs(residual) <= tolerance_micros:
        state, finality = "reconciled", "final"
    else:
        state, finality = "discrepant", "final"
    normalized_run = opaque_id("run", run_id) if run_id is not None else None
    material = {
        "run_id": normalized_run,
        "local_total": local_total,
        "provider_total": provider_total,
        "residual": residual,
        "tolerance": tolerance_micros,
        "state": state,
        "local_count": len(local),
        "provider_count": len(provider),
        "expected": expected,
        "observed": observed,
    }
    batch_id = opaque_id("reconciliation", canonical_json(material))
    now = datetime.now(timezone.utc).isoformat()
    timestamps = [row["occurred_at"] for row in rows]
    window_start = min(timestamps, default=now)
    window_end = max(timestamps, default=now)
    conn.execute(
        """
        INSERT OR REPLACE INTO reconciliation_batches(
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
            canonical_json({"local": bool(local), "provider_bill": bool(provider)}),
            None,
            "{}",
            window_start,
            window_end,
            canonical_json({"as_of": now}),
            expected,
            observed,
            len(local) if not provider else 0,
            len(provider) if not local else 0,
            local_total,
            provider_total,
            residual,
            tolerance_micros,
            finality,
            state,
            now,
            None,
        ),
    )
    conn.execute("DELETE FROM reconciliation_evidence WHERE batch_id = ?", (batch_id,))
    for row in local:
        conn.execute(
            "INSERT INTO reconciliation_evidence("
            "batch_id, observation_id, source_role, match_state) VALUES (?,?,?,?)",
            (batch_id, row["observation_id"], "local", "aggregate_constraint"),
        )
    for row in provider:
        conn.execute(
            "INSERT INTO reconciliation_evidence("
            "batch_id, observation_id, source_role, match_state) VALUES (?,?,?,?)",
            (batch_id, row["observation_id"], "provider_bill", "aggregate_constraint"),
        )
    conn.commit()
    return {**material, "batch_id": batch_id, "finality": finality}
