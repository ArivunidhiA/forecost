#!/usr/bin/env python3
"""Run deterministic local scale scenarios for the current receipt product."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from forecost.ledger.contracts import CausalIdentity
from forecost.ledger.evidence import append_observations, observation
from forecost.ledger.receipts import build_receipt
from forecost.ledger.schema import apply_schema
from forecost.reconciliation import reconcile_run
from forecost.resources import create_scope, release, reserve


def _span_id(index: int) -> str:
    return hashlib.sha256(f"benchmark:{index}".encode()).hexdigest()[:16]


def _observations(start: int, stop: int, *, charge_stride: int) -> Iterator:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    root_span = _span_id(0)
    for index in range(start, stop):
        causal = CausalIdentity(
            conversation_id="benchmark-conversation",
            trace_id="1234567890abcdef1234567890abcdef",
            run_id="benchmark-run",
            span_id=_span_id(index),
            parent_span_id=root_span if index else None,
            source_sequence=index * 3,
            idempotency_key=f"benchmark-span-{index}",
        )
        timestamp = base + timedelta(microseconds=index)
        yield observation(
            producer="offline_benchmark",
            event_kind="span",
            causal=causal,
            payload={
                "operation_kind": "agent" if index == 0 else "model",
                "lifecycle": "completed",
                "branch_id": f"branch-{index % 64}",
            },
            occurred_at=timestamp,
            observed_at=timestamp + timedelta(microseconds=1),
        )
        if index % charge_stride == 0:
            yield observation(
                producer="offline_benchmark",
                event_kind="charge",
                causal=replace(
                    causal,
                    source_sequence=index * 3 + 1,
                    idempotency_key=f"benchmark-local-{index}",
                ),
                payload={
                    "amount_micros": 1,
                    "currency": "USD",
                    "authority": "list_rate",
                    "line_item": "model_inference",
                    "finality": "final",
                },
                occurred_at=timestamp,
                observed_at=timestamp + timedelta(microseconds=1),
            )
            yield observation(
                producer="offline_benchmark",
                event_kind="charge",
                causal=replace(
                    causal,
                    source_sequence=index * 3 + 2,
                    idempotency_key=f"benchmark-provider-{index}",
                ),
                payload={
                    "amount_micros": 1,
                    "currency": "USD",
                    "authority": "billed",
                    "line_item": "model_inference",
                    "finality": "final",
                },
                occurred_at=timestamp,
                observed_at=timestamp + timedelta(microseconds=1),
            )


def _seconds(callable_) -> tuple[float, object]:
    started = time.perf_counter()
    value = callable_()
    return time.perf_counter() - started, value


def run_benchmarks(
    database: Path,
    sizes: list[int],
    *,
    receipt_limit: int,
    admission_sample: int,
    charge_stride: int = 100,
) -> list[dict[str, object]]:
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    apply_schema(conn)
    create_scope(conn, "benchmark-scope", "calls", max(sizes) + admission_sample + 1)
    results: list[dict[str, object]] = []
    previous = 0
    for size in sizes:
        ingest_seconds, batch = _seconds(
            lambda start=previous, stop=size: append_observations(
                conn,
                _observations(start, stop, charge_stride=charge_stride),
                batch_size=5_000,
            )
        )
        reconciliation_seconds, reconciliation = _seconds(
            lambda: reconcile_run(conn, "benchmark-run", tolerance_micros=0)
        )
        receipt_seconds: float | None = None
        receipt_spans: int | None = None
        if size <= receipt_limit:
            receipt_seconds, receipt = _seconds(
                lambda: build_receipt(conn, CausalIdentity(
                    "benchmark-conversation",
                    "1234567890abcdef1234567890abcdef",
                    "benchmark-run",
                    _span_id(0),
                ).normalized().run_id)
            )
            receipt_spans = len(receipt["causal_graph"])  # type: ignore[arg-type]
        admission_started = time.perf_counter()
        for index in range(admission_sample):
            item = reserve(
                conn,
                "benchmark-scope",
                1,
                f"history-{size}-sample-{index}",
            )
            release(conn, item.reservation_id)
        admission_seconds = time.perf_counter() - admission_started
        results.append(
            {
                "spans": size,
                "charge_stride": charge_stride,
                "new_observations": batch.inserted,  # type: ignore[attr-defined]
                "ingest_seconds": round(ingest_seconds, 6),
                "reconciliation_seconds": round(reconciliation_seconds, 6),
                "reconciliation_state": reconciliation["state"],  # type: ignore[index]
                "receipt_seconds": (
                    round(receipt_seconds, 6) if receipt_seconds is not None else None
                ),
                "receipt_spans": receipt_spans,
                "admission_sample": admission_sample,
                "admission_seconds": round(admission_seconds, 6),
                "database_bytes": database.stat().st_size,
            }
        )
        previous = size
    conn.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="40000,100000,250000,1000000")
    parser.add_argument("--receipt-limit", type=int, default=250_000)
    parser.add_argument("--admission-sample", type=int, default=1_000)
    parser.add_argument("--charge-stride", type=int, default=100)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    try:
        sizes = sorted({int(value) for value in args.sizes.split(",")})
    except ValueError as error:
        parser.error(f"invalid --sizes: {error}")
    if (
        not sizes
        or sizes[0] < 1
        or args.receipt_limit < 0
        or args.admission_sample < 1
        or args.charge_stride < 1
    ):
        parser.error(
            "sizes and admission sample must be positive; receipt limit cannot be negative"
        )
    if args.database is None:
        with tempfile.TemporaryDirectory(prefix="forecost-benchmark-") as directory:
            results = run_benchmarks(
                Path(directory) / "ledger.db",
                sizes,
                receipt_limit=args.receipt_limit,
                admission_sample=args.admission_sample,
                charge_stride=args.charge_stride,
            )
    else:
        results = run_benchmarks(
            args.database,
            sizes,
            receipt_limit=args.receipt_limit,
            admission_sample=args.admission_sample,
            charge_stride=args.charge_stride,
        )
    sys.stdout.write(json.dumps({"schema_version": 1, "results": results}, indent=2) + "\n")


if __name__ == "__main__":
    main()
