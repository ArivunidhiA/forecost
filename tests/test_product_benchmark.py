from __future__ import annotations

from scripts.benchmark_product import run_benchmarks


def test_product_benchmark_exercises_ingest_receipt_reconcile_and_admission(tmp_path):
    results = run_benchmarks(
        tmp_path / "benchmark.db",
        [200],
        receipt_limit=200,
        admission_sample=5,
    )

    assert len(results) == 1
    assert results[0]["spans"] == 200
    assert results[0]["new_observations"] == 204
    assert results[0]["receipt_spans"] == 200
    assert results[0]["reconciliation_state"] == "reconciled"
    database_bytes = results[0]["database_bytes"]
    assert isinstance(database_bytes, int)
    assert database_bytes > 0
