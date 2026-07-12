"""Tests for WriteQueue drop logging (B1 fix)."""

import logging
from queue import Full
from unittest.mock import patch

from forecost.db import WriteQueue


def test_write_queue_logs_when_full(caplog):
    """WriteQueue logs a warning when the queue is full and items are dropped."""
    wq = WriteQueue()

    with (
        patch.object(wq._queue, "put_nowait", side_effect=Full()),
        caplog.at_level(logging.WARNING, logger="forecost.db"),
    ):
        wq.put(
            project_id=1,
            timestamp="2026-01-01T00:00:00",
            model="gpt-4o",
            provider="openai",
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.01,
        )

    assert len(caplog.records) == 1
    assert "WriteQueue full" in caplog.records[0].message
    assert "gpt-4o" in caplog.records[0].message
