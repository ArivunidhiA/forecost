import json
import threading

import pytest
from click.testing import CliRunner

from llmcast.cli import main
from llmcast.db import (
    _insert_usage_logs_batch,
    create_project,
    get_or_create_db,
)
from llmcast.pricing import FALLBACK_PRICING
from llmcast.scope import analyze_heuristic
from llmcast.tracker import get_session_summary, log_call


@pytest.fixture
def cli_runner():
    return CliRunner()


def test_full_developer_workflow(cli_runner, tmp_path, db_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("import openai\n")
    (tmp_path / "README.md").write_text("chatbot\n")
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)

    result = cli_runner.invoke(main, ["init"])
    assert result.exit_code == 0

    result = cli_runner.invoke(main, ["status"])
    assert result.exit_code == 0

    result = cli_runner.invoke(main, ["forecast"])
    assert result.exit_code == 0

    result = cli_runner.invoke(main, ["forecast", "--json"])
    assert result.exit_code == 0

    result = cli_runner.invoke(main, ["track"])
    assert result.exit_code == 0

    result = cli_runner.invoke(main, ["forecast", "--brief"])
    assert result.exit_code == 0

    result = cli_runner.invoke(main, ["optimize"])
    assert result.exit_code == 0

    result = cli_runner.invoke(main, ["reset", "--yes"])
    assert result.exit_code == 0


def test_demo_command_works_standalone(cli_runner, db_path, monkeypatch):
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)
    result = cli_runner.invoke(main, ["demo"])
    assert result.exit_code == 0
    assert "Projected" in result.output


def test_init_reinit_flow(cli_runner, tmp_path, db_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("import openai\n")
    (tmp_path / "README.md").write_text("chatbot\n")
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)

    result = cli_runner.invoke(main, ["init"])
    assert result.exit_code == 0

    result = cli_runner.invoke(main, ["init"], input="y\n")
    assert result.exit_code == 0


def test_forecast_with_no_data_shows_baseline(cli_runner, tmp_path, db_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("import openai\n")
    (tmp_path / "README.md").write_text("chatbot\n")
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)

    result = cli_runner.invoke(main, ["init"])
    assert result.exit_code == 0

    result = cli_runner.invoke(main, ["forecast"])
    assert result.exit_code == 0


def test_forecast_json_schema_complete(cli_runner, tmp_path, db_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("import openai\n")
    (tmp_path / "README.md").write_text("chatbot\n")
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)

    result = cli_runner.invoke(main, ["init"])
    assert result.exit_code == 0

    conn = get_or_create_db()
    proj = conn.execute("SELECT id FROM projects WHERE path = ?", (str(tmp_path),)).fetchone()
    project_id = proj["id"]
    from datetime import datetime, timezone

    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    items = [
        (project_id, base.isoformat(), "gpt-4o-mini", "openai", 1000, 500, 0.50, None),
    ]
    _insert_usage_logs_batch(conn, items)

    result = cli_runner.invoke(main, ["forecast", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "project_id" in data
    assert "project_name" in data
    assert "actual_spend" in data
    assert "projected_total" in data
    assert "drift_status" in data
    assert "confidence" in data
    assert "model_breakdown" in data


def test_status_does_not_save_forecast(cli_runner, tmp_path, db_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("import openai\n")
    (tmp_path / "README.md").write_text("chatbot\n")
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)

    result = cli_runner.invoke(main, ["init"])
    assert result.exit_code == 0

    conn = get_or_create_db()
    proj = conn.execute("SELECT id FROM projects WHERE path = ?", (str(tmp_path),)).fetchone()
    project_id = proj["id"]
    from datetime import datetime, timezone

    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    items = [
        (project_id, base.isoformat(), "gpt-4o-mini", "openai", 1000, 500, 0.50, None),
    ]
    _insert_usage_logs_batch(conn, items)

    for _ in range(5):
        result = cli_runner.invoke(main, ["status"])
        assert result.exit_code == 0

    count = conn.execute("SELECT COUNT(*) AS n FROM forecasts").fetchone()["n"]
    assert count == 0

    result = cli_runner.invoke(main, ["forecast"])
    assert result.exit_code == 0
    count = conn.execute("SELECT COUNT(*) AS n FROM forecasts").fetchone()["n"]
    assert count == 1


def test_concurrent_tracking(db_path, monkeypatch):
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)
    tmp_path = db_path.parent
    project_id = create_project(
        name="concurrent",
        path=str(tmp_path),
        baseline_daily_cost=1.0,
        baseline_total_days=14,
        baseline_total_cost=14.0,
    )
    proj = {"id": project_id, "name": "concurrent", "path": str(tmp_path)}
    monkeypatch.setattr("llmcast.tracker._find_project", lambda: proj)

    import llmcast.tracker as mod

    mod._session_stats = {}

    def do_calls():
        for _ in range(20):
            log_call("gpt-4o-mini", 100, 50, provider="openai")

    threads = [threading.Thread(target=do_calls) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    summary = get_session_summary()
    assert summary["calls"] == 100


def test_pricing_coverage():
    assert len(FALLBACK_PRICING) >= 80
    from llmcast.pricing import calculate_cost

    assert calculate_cost("gpt-4o", 1000, 500) > 0
    assert calculate_cost("claude-3-5-sonnet-latest", 1000, 500) > 0
    assert calculate_cost("gemini-2.0-flash", 1000, 500) > 0


def test_scope_analyzer_realistic(tmp_path):
    (tmp_path / "main.py").write_text("import openai\n")
    (tmp_path / "README.md").write_text("RAG system for retrieval\n")
    result = analyze_heuristic(str(tmp_path))
    assert result["total_cost"] > 2.00
    assert result["project_type"] == "rag"


def test_disabled_env_var(monkeypatch):
    import httpx

    from llmcast import interceptor
    from llmcast.tracker import auto_track

    interceptor.uninstall()
    monkeypatch.setenv("LLMLAB_DISABLED", "1")
    original_send = httpx.Client.send
    auto_track()
    assert httpx.Client.send is original_send
