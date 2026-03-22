"""
Zero-maintenance SQLite database module for forecost cost tracking.
"""

import atexit
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue

__all__ = [
    "get_or_create_db",
    "create_project",
    "get_project_by_path",
    "get_daily_costs",
    "get_bucketed_costs",
    "get_recent_usage_logs",
    "get_active_days",
    "save_forecast",
    "get_forecast_history",
    "WriteQueue",
]

_DB_PATH = Path.home() / ".forecost" / "costs.db"
_BATCH_SIZE = 100
_FLUSH_INTERVAL = 2.0
_EXIT_TIMEOUT = 1.0

_conn: sqlite3.Connection | None = None
_conn_lock = threading.Lock()


def _ensure_dir() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            path TEXT NOT NULL UNIQUE,
            baseline_daily_cost REAL NOT NULL,
            baseline_total_days INTEGER NOT NULL,
            baseline_total_cost REAL NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id),
            timestamp TEXT NOT NULL,
            model TEXT NOT NULL,
            provider TEXT NOT NULL,
            tokens_in INTEGER NOT NULL,
            tokens_out INTEGER NOT NULL,
            cost_usd REAL NOT NULL,
            metadata TEXT,
            source TEXT DEFAULT 'api'
        );
        CREATE TABLE IF NOT EXISTS forecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id),
            iteration INTEGER NOT NULL,
            projected_total REAL NOT NULL,
            projected_remaining_days INTEGER NOT NULL,
            smoothed_burn_ratio REAL NOT NULL,
            confidence TEXT NOT NULL,
            active_days_count INTEGER NOT NULL,
            mape REAL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_usage_project_ts
            ON usage_logs(project_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_forecast_project_iter
            ON forecasts(project_id, iteration);
    """)


def get_or_create_db() -> sqlite3.Connection:
    global _conn
    with _conn_lock:
        if _conn is not None:
            return _conn
        _ensure_dir()
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _apply_pragmas(_conn)
        _init_schema(_conn)
        cols = [r[1] for r in _conn.execute("PRAGMA table_info(usage_logs)").fetchall()]
        if "source" not in cols:
            _conn.execute("ALTER TABLE usage_logs ADD COLUMN source TEXT DEFAULT 'api'")
            _conn.commit()
        return _conn


def create_project(
    name: str,
    path: str,
    baseline_daily_cost: float,
    baseline_total_days: int,
    baseline_total_cost: float,
    metadata: dict | None = None,
) -> int:
    conn = get_or_create_db()
    now = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata) if metadata is not None else None
    cur = conn.execute(
        """
        INSERT INTO projects (name, path, baseline_daily_cost,
            baseline_total_days, baseline_total_cost, metadata, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (name, path, baseline_daily_cost, baseline_total_days, baseline_total_cost, meta_json, now),
    )
    conn.commit()
    return cur.lastrowid


def get_project_by_path(path: str) -> dict | None:
    conn = get_or_create_db()
    row = conn.execute("SELECT * FROM projects WHERE path = ?", (path,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    if d.get("metadata"):
        d["metadata"] = json.loads(d["metadata"])
    return d


def get_daily_costs(project_id: int) -> list[tuple[str, float, int]]:
    conn = get_or_create_db()
    rows = conn.execute(
        """
        SELECT date(timestamp) AS day, SUM(cost_usd) AS cost,
               SUM(tokens_in + tokens_out) AS total_tokens
        FROM usage_logs
        WHERE project_id = ?
        GROUP BY day
        ORDER BY day
        """,
        (project_id,),
    ).fetchall()
    return [(r["day"], r["cost"], r["total_tokens"]) for r in rows]


def get_bucketed_costs(project_id: int, bucket_minutes: int = 15) -> list[tuple[str, float, int]]:
    """Aggregate costs into fixed time buckets.

    Only returns buckets that have actual costs (no zero-fill).
    Default 15-minute buckets give 16 data points per 4-hour session.
    """
    if bucket_minutes < 1:
        raise ValueError(f"bucket_minutes must be >= 1, got {bucket_minutes}")
    conn = get_or_create_db()
    rows = conn.execute(
        """
        SELECT
            strftime('%Y-%m-%d %H:', timestamp) ||
            printf('%02d', (CAST(strftime('%M', timestamp) AS INTEGER) / ?) * ?)
            AS bucket,
            SUM(cost_usd) AS cost,
            SUM(tokens_in + tokens_out) AS total_tokens
        FROM usage_logs
        WHERE project_id = ?
        GROUP BY bucket
        ORDER BY bucket
        """,
        (bucket_minutes, bucket_minutes, project_id),
    ).fetchall()
    return [(r["bucket"], r["cost"], r["total_tokens"]) for r in rows]


def get_recent_usage_logs(project_id: int, limit: int = 20) -> list[dict]:
    conn = get_or_create_db()
    rows = conn.execute(
        """
        SELECT id, project_id, timestamp, model, provider, tokens_in, tokens_out, cost_usd, metadata
        FROM usage_logs
        WHERE project_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_active_days(project_id: int) -> int:
    conn = get_or_create_db()
    row = conn.execute(
        "SELECT COUNT(DISTINCT date(timestamp)) AS cnt FROM usage_logs WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return row["cnt"] if row else 0


def save_forecast(
    project_id: int,
    iteration: int,
    projected_total: float,
    projected_remaining_days: int,
    smoothed_burn_ratio: float,
    confidence: str,
    active_days_count: int,
    mape: float | None = None,
) -> int:
    conn = get_or_create_db()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO forecasts (project_id, iteration, projected_total, projected_remaining_days,
            smoothed_burn_ratio, confidence, active_days_count, mape, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            iteration,
            projected_total,
            projected_remaining_days,
            smoothed_burn_ratio,
            confidence,
            active_days_count,
            mape,
            now,
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_forecast_history(project_id: int) -> list[dict]:
    conn = get_or_create_db()
    rows = conn.execute(
        """
        SELECT id, project_id, iteration, projected_total, projected_remaining_days,
               smoothed_burn_ratio, confidence, active_days_count, mape, created_at
        FROM forecasts
        WHERE project_id = ?
        ORDER BY iteration
        """,
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _insert_usage_logs_batch(conn: sqlite3.Connection, items: list[tuple]) -> None:
    if not items:
        return
    normalized = [item if len(item) >= 9 else (*item, "api") for item in items]
    conn.executemany(
        """
        INSERT INTO usage_logs (project_id, timestamp, model, provider,
            tokens_in, tokens_out, cost_usd, metadata, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        normalized,
    )
    conn.commit()


class WriteQueue:
    """
    Async batch writer for usage_logs. Flushes every 100 items or 2 seconds.
    Never blocks the main thread. Registers atexit handler with 1s timeout.
    """

    def __init__(self) -> None:
        self._queue: Queue[tuple | None] = Queue(maxsize=10_000)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        atexit.register(self._on_exit)

    def put(
        self,
        project_id: int,
        timestamp: str,
        model: str,
        provider: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        metadata: str | None = None,
        source: str = "api",
    ) -> None:
        try:
            item = (
                project_id,
                timestamp,
                model,
                provider,
                tokens_in,
                tokens_out,
                cost_usd,
                metadata,
                source,
            )
            self._queue.put_nowait(item)
        except Exception:
            pass  # Drop item if queue is full — never block the caller

    def _worker(self) -> None:
        _ensure_dir()
        writer_conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _apply_pragmas(writer_conn)
        batch: list[tuple] = []
        last_flush = time.monotonic()
        while True:
            try:
                item = self._queue.get(timeout=0.1)
            except Empty:
                now = time.monotonic()
                if batch and (now - last_flush) >= _FLUSH_INTERVAL:
                    self._flush(batch, writer_conn)
                    batch = []
                    last_flush = now
                continue
            if item is None:
                self._flush(batch, writer_conn)
                writer_conn.close()
                break
            batch.append(item)
            now = time.monotonic()
            if len(batch) >= _BATCH_SIZE or (now - last_flush) >= _FLUSH_INTERVAL:
                self._flush(batch, writer_conn)
                batch = []
                last_flush = now

    def _flush(self, batch: list[tuple], conn: sqlite3.Connection) -> None:
        if not batch:
            return
        log_path = Path.home() / ".forecost" / "error.log"
        recovery_path = Path.home() / ".forecost" / "recovery.jsonl"
        try:
            _insert_usage_logs_batch(conn, batch)
        except Exception as e:
            _ensure_dir()
            try:
                with open(log_path, "a") as f:
                    f.write(f"[db] {e!r}\n")
            except OSError:
                pass
            time.sleep(0.5)
            try:
                _insert_usage_logs_batch(conn, batch)
            except Exception:
                try:
                    try:
                        if os.path.getsize(recovery_path) > 1_000_000:
                            with open(recovery_path, "r") as rf:
                                lines = rf.readlines()[-100:]
                            with open(recovery_path, "w") as wf:
                                wf.writelines(lines)
                    except OSError:
                        pass
                    with open(recovery_path, "a") as f:
                        for item in batch:
                            d = {
                                "project_id": item[0],
                                "timestamp": item[1],
                                "model": item[2],
                                "provider": item[3],
                                "tokens_in": item[4],
                                "tokens_out": item[5],
                                "cost_usd": item[6],
                                "metadata": item[7],
                                "source": item[8] if len(item) > 8 else "api",
                            }
                            f.write(json.dumps(d) + "\n")
                except OSError:
                    pass

    def _on_exit(self) -> None:
        try:
            self._queue.put(None, timeout=_EXIT_TIMEOUT)
        except Exception:
            return
        self._thread.join(timeout=_EXIT_TIMEOUT)
