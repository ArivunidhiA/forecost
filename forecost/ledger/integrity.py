"""Local tamper-evidence for the append-only causal journal.

The chain detects accidental damage and unsophisticated rewrites.  It is not a
signature and cannot defend against the same OS user deliberately rewriting
both the journal and its local head record.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal

CHAIN_ID = "causal-observations-v1"
GENESIS_DIGEST = hashlib.sha256(CHAIN_ID.encode("ascii")).hexdigest()
IntegrityState = Literal[
    "intact",
    "truncated",
    "rewritten",
    "deleted",
    "reordered",
    "duplicated",
    "forked",
    "unanchored",
    "unknown",
]


@dataclass(frozen=True)
class JournalVerification:
    state: IntegrityState
    event_count: int
    anchored_count: int
    head_sequence: int
    first_bad_sequence: int | None
    detail: str
    threat_boundary: str = (
        "local tamper-evidence only; the same OS user can replace evidence and its anchor"
    )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def entry_digest(row: sqlite3.Row | dict[str, object], sequence: int, previous: str) -> str:
    material = {
        "journal_sequence": sequence,
        "previous_digest": previous,
        "observation_id": row["observation_id"],
        "schema_version": row["schema_version"],
        "producer": row["producer"],
        "source_sequence": row["source_sequence"],
        "idempotency_key": row["idempotency_key"],
        "event_kind": row["event_kind"],
        "occurred_at": row["occurred_at"],
        "observed_at": row["observed_at"],
        "causal_json": row["causal_json"],
        "payload_json": row["payload_json"],
        "supersedes_observation_id": row["supersedes_observation_id"],
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def initialize_journal_chain(conn: sqlite3.Connection) -> None:
    """Anchor an existing unchained journal in deterministic projection order."""
    rows = conn.execute(
        "SELECT * FROM journal_observations ORDER BY producer, source_sequence, idempotency_key"
    ).fetchall()
    previous = GENESIS_DIGEST
    for sequence, row in enumerate(rows, start=1):
        digest = entry_digest(row, sequence, previous)
        conn.execute(
            "UPDATE journal_observations SET journal_sequence=?, previous_digest=?, "
            "entry_digest=? WHERE observation_id=?",
            (sequence, previous, digest, row["observation_id"]),
        )
        previous = digest
    _write_head(conn, len(rows), previous)


def chain_tail(conn: sqlite3.Connection) -> tuple[int, str]:
    row = conn.execute(
        "SELECT event_count, head_digest FROM journal_integrity_heads WHERE chain_id=?",
        (CHAIN_ID,),
    ).fetchone()
    if row is None:
        initialize_journal_chain(conn)
        row = conn.execute(
            "SELECT event_count, head_digest FROM journal_integrity_heads WHERE chain_id=?",
            (CHAIN_ID,),
        ).fetchone()
    if row is None:  # pragma: no cover - initialization invariant
        raise RuntimeError("journal integrity head was not initialized")
    return int(row["event_count"]), str(row["head_digest"])


def advance_chain(conn: sqlite3.Connection, observation_id: str) -> tuple[int, str, str]:
    """Attach one newly inserted row to the current chain inside its transaction."""
    sequence, previous = chain_tail(conn)
    sequence += 1
    row = conn.execute(
        "SELECT * FROM journal_observations WHERE observation_id=?", (observation_id,)
    ).fetchone()
    if row is None:  # pragma: no cover - caller inserts first
        raise RuntimeError("cannot chain a missing observation")
    digest = entry_digest(row, sequence, previous)
    conn.execute(
        "UPDATE journal_observations SET journal_sequence=?, previous_digest=?, entry_digest=? "
        "WHERE observation_id=?",
        (sequence, previous, digest, observation_id),
    )
    _write_head(conn, sequence, digest)
    return sequence, previous, digest


def _write_head(conn: sqlite3.Connection, sequence: int, digest: str) -> None:
    conn.execute(
        "INSERT INTO journal_integrity_heads("
        "chain_id,event_count,head_sequence,head_digest,updated_at) "
        "VALUES (?,?,?,?,?) ON CONFLICT(chain_id) DO UPDATE SET "
        "event_count=excluded.event_count, head_sequence=excluded.head_sequence, "
        "head_digest=excluded.head_digest, updated_at=excluded.updated_at",
        (CHAIN_ID, sequence, sequence, digest, datetime.now(timezone.utc).isoformat()),
    )


def verify_journal_chain(conn: sqlite3.Connection) -> JournalVerification:
    rows = conn.execute(
        "SELECT * FROM journal_observations ORDER BY journal_sequence, observation_id"
    ).fetchall()
    head = conn.execute(
        "SELECT event_count,head_sequence,head_digest "
        "FROM journal_integrity_heads WHERE chain_id=?",
        (CHAIN_ID,),
    ).fetchone()
    if head is None:
        state: IntegrityState = "unanchored" if not rows else "unknown"
        return JournalVerification(state, len(rows), 0, 0, None, "journal has no chain anchor")

    anchored_count = int(head["event_count"])
    head_sequence = int(head["head_sequence"])
    if not rows:
        state = "intact" if anchored_count == 0 else "truncated"
        detail = "empty anchored journal" if state == "intact" else "all anchored tail rows missing"
        return JournalVerification(state, 0, anchored_count, head_sequence, 1, detail)

    sequences = [row["journal_sequence"] for row in rows]
    if any(
        value is None or isinstance(value, bool) or not isinstance(value, int)
        for value in sequences
    ):
        return JournalVerification(
            "unknown", len(rows), anchored_count, head_sequence, None, "unchained row present"
        )
    integer_sequences = [int(value) for value in sequences]
    if len(set(integer_sequences)) != len(integer_sequences):
        return JournalVerification(
            "duplicated", len(rows), anchored_count, head_sequence, None, "duplicate sequence"
        )
    digests = [str(row["entry_digest"]) for row in rows]
    if len(set(digests)) != len(digests):
        return JournalVerification(
            "duplicated", len(rows), anchored_count, head_sequence, None, "duplicate entry digest"
        )
    previous_counts: dict[str, int] = {}
    for row in rows:
        previous = str(row["previous_digest"])
        previous_counts[previous] = previous_counts.get(previous, 0) + 1
    if any(count > 1 for previous, count in previous_counts.items() if previous != GENESIS_DIGEST):
        return JournalVerification(
            "forked",
            len(rows),
            anchored_count,
            head_sequence,
            None,
            "multiple children share a parent",
        )

    expected_sequence = 1
    expected_previous = GENESIS_DIGEST
    known_digests = set(digests)
    for row in rows:
        actual_sequence = int(row["journal_sequence"])
        if actual_sequence != expected_sequence:
            if actual_sequence > expected_sequence:
                return JournalVerification(
                    "deleted",
                    len(rows),
                    anchored_count,
                    head_sequence,
                    expected_sequence,
                    "an internal journal sequence is missing",
                )
            return JournalVerification(
                "reordered",
                len(rows),
                anchored_count,
                head_sequence,
                actual_sequence,
                "sequence regressed",
            )
        previous = str(row["previous_digest"])
        if previous != expected_previous:
            state = "reordered" if previous in known_digests else "forked"
            return JournalVerification(
                state,
                len(rows),
                anchored_count,
                head_sequence,
                actual_sequence,
                "entry does not extend the immediately preceding digest",
            )
        expected_digest = entry_digest(row, actual_sequence, previous)
        if row["entry_digest"] != expected_digest:
            return JournalVerification(
                "rewritten",
                len(rows),
                anchored_count,
                head_sequence,
                actual_sequence,
                "entry material no longer matches its digest",
            )
        expected_previous = expected_digest
        expected_sequence += 1

    if len(rows) < anchored_count and expected_previous != head["head_digest"]:
        return JournalVerification(
            "truncated",
            len(rows),
            anchored_count,
            head_sequence,
            len(rows) + 1,
            "valid prefix remains but the anchored tail is missing",
        )
    if len(rows) != anchored_count or head_sequence != anchored_count:
        return JournalVerification(
            "unknown", len(rows), anchored_count, head_sequence, None, "chain/head counts disagree"
        )
    if expected_previous != head["head_digest"]:
        return JournalVerification(
            "forked",
            len(rows),
            anchored_count,
            head_sequence,
            len(rows),
            "chain head differs from anchor",
        )
    return JournalVerification(
        "intact", len(rows), anchored_count, head_sequence, None, "journal chain and anchor agree"
    )
