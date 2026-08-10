from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from forecost.commands.verify_cmd import verify
from forecost.lab import seed_demo
from forecost.ledger.contracts import CausalIdentity
from forecost.ledger.evidence import (
    append_observation,
    append_observations,
    observation,
    rebuild_projections,
)
from forecost.ledger.integrity import verify_journal_chain


def _spans(count: int):
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for sequence in range(1, count + 1):
        causal = CausalIdentity(
            "batch-conversation",
            "1" * 32,
            "batch-run",
            f"{sequence:016x}",
            source_sequence=sequence,
            idempotency_key=f"event-{sequence}",
        )
        yield observation(
            producer="batch-test",
            event_kind="span",
            causal=causal,
            payload={"operation_kind": "agent", "lifecycle": "completed"},
            occurred_at=when,
            observed_at=when,
        )


def test_bounded_batch_append_is_replay_safe_and_integrity_anchored(ledger_conn):
    result = append_observations(ledger_conn, _spans(503), batch_size=100)
    replay = append_observations(ledger_conn, _spans(503), batch_size=128)

    assert (result.inserted, result.duplicates, result.batches) == (503, 0, 6)
    assert (replay.inserted, replay.duplicates, replay.batches) == (0, 503, 4)
    assert ledger_conn.execute("SELECT COUNT(*) FROM causal_spans").fetchone()[0] == 503
    verification = verify_journal_chain(ledger_conn)
    assert verification.state == "intact"
    assert verification.event_count == 503


def test_conflict_rolls_back_the_current_bounded_batch(ledger_conn):
    item = next(iter(_spans(1)))
    conflict = observation(
        producer=item.producer,
        event_kind="span",
        causal=item.causal,
        payload={"operation_kind": "agent", "lifecycle": "failed"},
        occurred_at=item.occurred_at,
        observed_at=item.observed_at,
    )

    with pytest.raises(ValueError, match="different evidence"):
        append_observations(ledger_conn, [item, conflict], batch_size=2)

    assert ledger_conn.execute("SELECT COUNT(*) FROM journal_observations").fetchone()[0] == 0
    assert verify_journal_chain(ledger_conn).state == "intact"


def test_incremental_projection_matches_rebuild_for_out_of_order_lifecycle(ledger_conn):
    items = list(_spans(2))
    # Two observations for one span: completed has the greater source order but arrives first.
    completed = items[1]
    earlier = observation(
        producer="batch-test",
        event_kind="span",
        causal=CausalIdentity(
            "batch-conversation",
            "1" * 32,
            "batch-run",
            completed.causal.span_id,
            source_sequence=1,
            idempotency_key="earlier-lifecycle",
        ),
        payload={"operation_kind": "agent", "lifecycle": "running"},
        occurred_at=completed.occurred_at,
        observed_at=completed.observed_at,
    )
    append_observation(ledger_conn, completed)
    append_observation(ledger_conn, earlier)
    normalized_run_id = completed.normalized().causal.run_id
    before = tuple(
        ledger_conn.execute(
            "SELECT lifecycle,source_order FROM causal_runs WHERE run_id=?",
            (normalized_run_id,),
        ).fetchone()
    )
    rebuild_projections(ledger_conn)
    after = tuple(
        ledger_conn.execute(
            "SELECT lifecycle,source_order FROM causal_runs WHERE run_id=?",
            (normalized_run_id,),
        ).fetchone()
    )
    assert before == after
    assert before[0] == "completed"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("truncate", "truncated"),
        ("delete", "deleted"),
        ("rewrite", "rewritten"),
        ("reorder", "reordered"),
        ("duplicate", "duplicated"),
        ("fork", "forked"),
        ("unanchor", "unknown"),
    ],
)
def test_journal_mutation_classes_are_deterministic(ledger_conn, mutation, expected):
    seed_demo(ledger_conn, seed=902)
    rows = ledger_conn.execute(
        "SELECT observation_id,journal_sequence,previous_digest,entry_digest "
        "FROM journal_observations ORDER BY journal_sequence"
    ).fetchall()
    assert len(rows) >= 3
    if mutation == "truncate":
        ledger_conn.execute(
            "DELETE FROM journal_observations WHERE journal_sequence=?", (len(rows),)
        )
    elif mutation == "delete":
        ledger_conn.execute("DELETE FROM journal_observations WHERE journal_sequence=2")
    elif mutation == "rewrite":
        ledger_conn.execute(
            "UPDATE journal_observations SET payload_json='{}' WHERE journal_sequence=2"
        )
    elif mutation == "reorder":
        ledger_conn.execute(
            "UPDATE journal_observations SET previous_digest=? WHERE journal_sequence=2",
            (rows[-1]["entry_digest"],),
        )
    elif mutation == "duplicate":
        ledger_conn.execute("DROP INDEX idx_journal_sequence")
        ledger_conn.execute(
            "UPDATE journal_observations SET journal_sequence=2 WHERE journal_sequence=3"
        )
    elif mutation == "fork":
        ledger_conn.execute(
            "UPDATE journal_observations SET previous_digest=? WHERE journal_sequence=3",
            (rows[1]["previous_digest"],),
        )
    else:
        ledger_conn.execute("DELETE FROM journal_integrity_heads")
    ledger_conn.commit()

    first = verify_journal_chain(ledger_conn)
    second = verify_journal_chain(ledger_conn)
    assert first == second
    assert first.state == expected


def test_verify_json_is_one_machine_readable_document_on_failure(ledger_conn, monkeypatch):
    seed_demo(ledger_conn, seed=903)
    ledger_conn.execute(
        "UPDATE journal_observations SET payload_json='{}' WHERE journal_sequence=2"
    )
    ledger_conn.commit()
    monkeypatch.setattr("forecost.commands.verify_cmd.get_ledger_db", lambda: ledger_conn)

    result = CliRunner().invoke(verify, ["--json-output"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["overall_state"] == "rewritten"
    assert payload["journal"]["state"] == "rewritten"
    assert "same OS user" in payload["journal"]["threat_boundary"]
