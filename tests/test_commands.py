import json
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import HTTPServer

import pytest
from click.testing import CliRunner

from llmcast.cli import main
from llmcast.commands.serve_cmd import LLMLabHandler
from llmcast.db import (
    _insert_usage_logs_batch,
    create_project,
    get_or_create_db,
    get_project_by_path,
)
from llmcast.interceptor import log_stream_usage, set_project_id


@pytest.fixture
def cli_runner():
    return CliRunner()


def _init_project(cli_runner, tmp_path, db_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("import openai\n")
    (tmp_path / "README.md").write_text("chatbot\n")
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)
    result = cli_runner.invoke(main, ["init"])
    assert result.exit_code == 0
    return result


def _insert_test_data(tmp_path, db_path):
    conn = get_or_create_db()
    proj = conn.execute("SELECT id FROM projects WHERE path = ?", (str(tmp_path),)).fetchone()
    project_id = proj["id"]
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    items = [
        (project_id, base.isoformat(), "gpt-4o-mini", "openai", 1000, 500, 0.50, None),
    ]
    _insert_usage_logs_batch(conn, items)
    return project_id


def test_export_csv(cli_runner, tmp_path, db_path, monkeypatch):
    _init_project(cli_runner, tmp_path, db_path, monkeypatch)
    _insert_test_data(tmp_path, db_path)
    result = cli_runner.invoke(main, ["export", "--format", "csv"])
    assert result.exit_code == 0
    assert "timestamp,model" in result.output


def test_export_json(cli_runner, tmp_path, db_path, monkeypatch):
    _init_project(cli_runner, tmp_path, db_path, monkeypatch)
    _insert_test_data(tmp_path, db_path)
    result = cli_runner.invoke(main, ["export", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "timestamp" in data[0] and "model" in data[0]


def test_forecast_output_markdown(cli_runner, tmp_path, db_path, monkeypatch):
    _init_project(cli_runner, tmp_path, db_path, monkeypatch)
    _insert_test_data(tmp_path, db_path)
    result = cli_runner.invoke(main, ["forecast", "--output", "markdown"])
    assert result.exit_code == 0
    assert "## Cost Forecast" in result.output
    assert "| Metric |" in result.output


def test_forecast_output_csv(cli_runner, tmp_path, db_path, monkeypatch):
    _init_project(cli_runner, tmp_path, db_path, monkeypatch)
    _insert_test_data(tmp_path, db_path)
    result = cli_runner.invoke(main, ["forecast", "--output", "csv"])
    assert result.exit_code == 0
    assert "metric,value" in result.output


def test_forecast_exit_code_on_budget(cli_runner, tmp_path, db_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("import openai\n")
    (tmp_path / "README.md").write_text("chatbot\n")
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)
    result = cli_runner.invoke(main, ["init", "--budget", "1000"])
    assert result.exit_code == 0
    _insert_test_data(tmp_path, db_path)
    result = cli_runner.invoke(main, ["forecast", "--exit-code"])
    assert result.exit_code == 0


def test_forecast_exit_code_over_budget(cli_runner, tmp_path, db_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("import openai\n")
    (tmp_path / "README.md").write_text("chatbot\n")
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)
    result = cli_runner.invoke(main, ["init", "--budget", "1"])
    assert result.exit_code == 0
    conn = get_or_create_db()
    proj = conn.execute("SELECT id FROM projects WHERE path = ?", (str(tmp_path),)).fetchone()
    project_id = proj["id"]
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    items = [
        (project_id, base.isoformat(), "gpt-4o", "openai", 50000, 20000, 50.0, None),
    ]
    _insert_usage_logs_batch(conn, items)
    result = cli_runner.invoke(main, ["forecast", "--exit-code"])
    assert result.exit_code == 2


def test_reset_keep_data(cli_runner, tmp_path, db_path, monkeypatch):
    _init_project(cli_runner, tmp_path, db_path, monkeypatch)
    project_id = _insert_test_data(tmp_path, db_path)
    conn = get_or_create_db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM usage_logs WHERE project_id = ?", (project_id,)
    ).fetchone()
    before = row["n"]
    assert before == 1
    result = cli_runner.invoke(main, ["reset", "--keep-data", "--yes"])
    assert result.exit_code == 0
    assert get_project_by_path(str(tmp_path)) is None
    after = conn.execute("SELECT COUNT(*) AS n FROM usage_logs").fetchone()["n"]
    assert after == 1


def test_reset_full(cli_runner, tmp_path, db_path, monkeypatch):
    _init_project(cli_runner, tmp_path, db_path, monkeypatch)
    _insert_test_data(tmp_path, db_path)
    result = cli_runner.invoke(main, ["reset", "--yes"])
    assert result.exit_code == 0
    assert get_project_by_path(str(tmp_path)) is None
    conn = get_or_create_db()
    assert conn.execute("SELECT COUNT(*) AS n FROM usage_logs").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM forecasts").fetchone()["n"] == 0


def test_serve_health(db_path, monkeypatch):
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)
    server = HTTPServer(("127.0.0.1", 0), LLMLabHandler)
    port = server.server_address[1]
    done = threading.Event()

    def run():
        server.serve_forever()
        done.set()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as resp:
            data = json.loads(resp.read().decode())
            assert data == {"status": "ok"}
    finally:
        server.shutdown()


def test_log_stream_usage_openai_format(db_path, monkeypatch):
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)
    monkeypatch.setattr("llmcast.interceptor._write_queue", None)
    project_id = create_project(
        name="test",
        path="/tmp/test",
        baseline_daily_cost=1.0,
        baseline_total_days=14,
        baseline_total_cost=14.0,
    )
    set_project_id(project_id)
    log_stream_usage(
        {
            "model": "gpt-4o-mini",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
    )
    time.sleep(2.5)
    conn = get_or_create_db()
    rows = conn.execute("SELECT * FROM usage_logs WHERE project_id = ?", (project_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["model"] == "gpt-4o-mini"
    assert rows[0]["tokens_in"] == 100
    assert rows[0]["tokens_out"] == 50


def test_log_stream_usage_anthropic_format(db_path, monkeypatch):
    monkeypatch.setattr("llmcast.db._DB_PATH", db_path)
    monkeypatch.setattr("llmcast.db._conn", None)
    monkeypatch.setattr("llmcast.interceptor._write_queue", None)
    project_id = create_project(
        name="test2",
        path="/tmp/test2",
        baseline_daily_cost=1.0,
        baseline_total_days=14,
        baseline_total_cost=14.0,
    )
    set_project_id(project_id)
    log_stream_usage(
        {
            "model": "claude-3-5-sonnet-20241022",
            "usage": {"input_tokens": 200, "output_tokens": 80},
        }
    )
    time.sleep(2.5)
    conn = get_or_create_db()
    rows = conn.execute("SELECT * FROM usage_logs WHERE project_id = ?", (project_id,)).fetchall()
    assert len(rows) == 1
    assert "claude" in rows[0]["model"].lower()
    assert rows[0]["tokens_in"] == 200
    assert rows[0]["tokens_out"] == 80
