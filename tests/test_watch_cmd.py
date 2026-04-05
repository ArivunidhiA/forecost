"""Tests for forecost watch command display builder."""

from unittest.mock import MagicMock, patch

from rich.table import Table
from rich.text import Text

from forecost.commands.watch_cmd import _build_display


@patch("forecost.commands.watch_cmd.get_or_create_db")
@patch("forecost.commands.watch_cmd.get_recent_usage_logs")
@patch("forecost.commands.watch_cmd.get_daily_costs")
def test_build_display_with_data(mock_daily, mock_logs, mock_db):
    """_build_display returns two Table renderables when data is present."""
    mock_daily.return_value = [("2025-04-01", 5.0), ("2025-04-02", 3.0)]
    mock_logs.return_value = [
        {
            "timestamp": "2025-04-02T10:00:00",
            "model": "gpt-4o-mini",
            "tokens_in": 500,
            "tokens_out": 200,
            "cost_usd": 0.001,
        },
    ]
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.side_effect = [
        {"cnt": 10},
        {"tok": 7000},
    ]
    mock_db.return_value = mock_conn

    project = {"id": 1, "name": "test"}
    summary, details = _build_display(project)
    assert isinstance(summary, Table)
    assert isinstance(details, Table)


@patch("forecost.commands.watch_cmd.get_or_create_db")
@patch("forecost.commands.watch_cmd.get_recent_usage_logs")
@patch("forecost.commands.watch_cmd.get_daily_costs")
def test_build_display_empty_data(mock_daily, mock_logs, mock_db):
    """_build_display handles empty data gracefully."""
    mock_daily.return_value = []
    mock_logs.return_value = []
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.side_effect = [
        {"cnt": 0},
        {"tok": 0},
    ]
    mock_db.return_value = mock_conn

    project = {"id": 1, "name": "test"}
    summary, details = _build_display(project)
    assert isinstance(summary, Table)
    assert isinstance(details, Text)
    assert "no calls" in details.plain.lower()
