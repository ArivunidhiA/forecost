# Performance contract

Forecost is a local SQLite product. The performance goal is predictable bounded
work, not a universal throughput number. Results depend on filesystem, Python,
SQLite, durability settings, graph shape, and evidence mix.

## Required complexity

- Single observation append: indexed idempotency check plus incremental
  projection and integrity-chain update; never a full-history projection rebuild.
- Batch ingestion: bounded transactions of at most 10,000 observations.
- Admission: O(number of applicable rules), independent of journal history,
  using transactional scope counters.
- Reconciliation: set-based authority selection and streaming evidence IDs;
  no Python materialization of the charge history.
- Receipt: O(spans + meters + active charges + outcome evidence) because the
  portable artifact contains those records. CLI output must have an explicit
  practical size boundary before a million-span full graph is called supported.

## Local benchmark matrix

`scripts/benchmark_product.py` creates a deterministic content-free graph with
independent local and billed valuations. It measures incremental ingestion,
set reconciliation, receipt construction through 250k spans by default, and a
fixed admission sample after histories of 40k, 100k, 250k, and 1M spans.

```bash
python -m scripts.benchmark_product \
  --sizes 40000,100000,250000,1000000 \
  --receipt-limit 250000 --admission-sample 1000
```

The command emits stable JSON field names but observed timings are machine
evidence, not constants checked into marketing copy.

## Initial release budgets

- Hook/gate hot path: p95 at or below 50 ms on the release test host.
- Admission median must not materially increase from 40k to 1M history; a 2x
  regression is a release blocker pending explanation.
- Ingestion must scale approximately linearly across the matrix; any interval
  with more than 3x per-observation degradation is a release blocker.
- Reconciliation must complete without unbounded Python memory growth.
- Full graph receipt construction is supported only through the measured
  receipt limit. Larger histories require a bounded summary/export path before
  a support claim is added.

The final QA evidence records host details, exact commit, database size, and
results. A benchmark script existing is not evidence that its targets pass.

## Latest local evidence

The 2026-08-09 M3 Pro/Python 3.12 run is stored at
[`qa/evidence/performance-2026-08-09.json`](qa/evidence/performance-2026-08-09.json).
It exercised 1,020,000 observations and found a missing supersession index that
made 20k-charge reconciliation take roughly 157 seconds. After the index and
set-key fix, the same charge-density probe completed in roughly 0.30 seconds.

Full graph receipts were measured through 250k spans (3.51 seconds on that
host). A million-span full graph receipt is deliberately unsupported until a
bounded summary/export interface exists; the million-span ingest and flat
admission measurements do not override that output-size boundary.
