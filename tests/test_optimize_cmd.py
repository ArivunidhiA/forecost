"""Tests for forecost optimize command."""

from datetime import datetime, timedelta, timezone

from click.testing import CliRunner

from forecost.cli import main
from forecost.db import create_project, get_or_create_db
from forecost.pricing import calculate_cost


def test_optimize_no_project(tmp_path, monkeypatch, db_path):
    """Running optimize without an initialized project should error."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["optimize"])
    assert result.exit_code != 0
    assert "init" in result.output.lower()


def test_optimize_no_usage_data(tmp_path, monkeypatch, db_path):
    """Optimize with no usage logs should report no data."""
    monkeypatch.chdir(tmp_path)
    create_project(
        name="test-opt",
        path=str(tmp_path),
        baseline_daily_cost=10.0,
        baseline_total_days=14,
        baseline_total_cost=140.0,
    )
    runner = CliRunner()
    result = runner.invoke(main, ["optimize"])
    assert result.exit_code == 0
    assert "no usage data" in result.output.lower()


def test_optimize_with_expensive_model(tmp_path, monkeypatch, db_path):
    """Optimize with an expensive Tier 1 model should suggest cheaper alternatives."""
    monkeypatch.chdir(tmp_path)
    project_id = create_project(
        name="test-expensive",
        path=str(tmp_path),
        baseline_daily_cost=10.0,
        baseline_total_days=14,
        baseline_total_cost=140.0,
    )
    conn = get_or_create_db()
    base = datetime.now(timezone.utc)
    for i in range(20):
        ts = (base - timedelta(hours=i)).isoformat()
        cost = calculate_cost("gpt-4-turbo", 2000, 500)
        conn.execute(
            "INSERT INTO usage_logs (project_id, timestamp, model, provider, "
            "tokens_in, tokens_out, cost_usd, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, ts, "gpt-4-turbo", "openai", 2000, 500, cost, None),
        )
    conn.commit()
    runner = CliRunner()
    result = runner.invoke(main, ["optimize"])
    assert result.exit_code == 0
    assert "gpt-4o" in result.output.lower() or "saving" in result.output.lower()


def test_optimize_with_cheap_model(tmp_path, monkeypatch, db_path):
    """Optimize with a cheap Tier 2/3 model should say choices look efficient."""
    monkeypatch.chdir(tmp_path)
    project_id = create_project(
        name="test-cheap",
        path=str(tmp_path),
        baseline_daily_cost=1.0,
        baseline_total_days=14,
        baseline_total_cost=14.0,
    )
    conn = get_or_create_db()
    base = datetime.now(timezone.utc)
    for i in range(20):
        ts = (base - timedelta(hours=i)).isoformat()
        cost = calculate_cost("gpt-4o-mini", 500, 200)
        conn.execute(
            "INSERT INTO usage_logs (project_id, timestamp, model, provider, "
            "tokens_in, tokens_out, cost_usd, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, ts, "gpt-4o-mini", "openai", 500, 200, cost, None),
        )
    conn.commit()
    runner = CliRunner()
    result = runner.invoke(main, ["optimize"])
    assert result.exit_code == 0
    assert "efficient" in result.output.lower() or "no" in result.output.lower()
