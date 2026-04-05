"""Tests for forecost serve command HTTP API endpoints."""

import json
import socket
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer

from forecost.commands.serve_cmd import ForecostHandler
from forecost.db import create_project, get_or_create_db
from forecost.pricing import calculate_cost


def _free_port():
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(port):
    server = HTTPServer(("127.0.0.1", port), ForecostHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _get(port, path):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url)  # noqa: S310
    try:
        resp = urllib.request.urlopen(req, timeout=5)  # noqa: S310
        body = json.loads(resp.read().decode())
        headers = dict(resp.headers)
        return resp.status, body, headers
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode())
        headers = dict(e.headers)
        return e.code, body, headers


def test_serve_health_endpoint(tmp_path, monkeypatch, db_path):
    """GET /api/health should return 200 with status ok."""
    monkeypatch.chdir(tmp_path)
    port = _free_port()
    server = _start_server(port)
    try:
        status, body, _ = _get(port, "/api/health")
        assert status == 200
        assert body["status"] == "ok"
    finally:
        server.shutdown()


def test_serve_forecast_endpoint(tmp_path, monkeypatch, db_path):
    """GET /api/forecast should return 200 with projected_total."""
    monkeypatch.chdir(tmp_path)
    project_id = create_project(
        name="serve-test",
        path=str(tmp_path),
        baseline_daily_cost=10.0,
        baseline_total_days=14,
        baseline_total_cost=140.0,
    )
    conn = get_or_create_db()
    base = datetime.now(timezone.utc)
    for i in range(5):
        ts = (base - timedelta(days=i)).isoformat()
        cost = calculate_cost("gpt-4o-mini", 1000, 500)
        conn.execute(
            "INSERT INTO usage_logs (project_id, timestamp, model, provider, "
            "tokens_in, tokens_out, cost_usd, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, ts, "gpt-4o-mini", "openai", 1000, 500, cost, None),
        )
    conn.commit()

    port = _free_port()
    server = _start_server(port)
    try:
        status, body, _ = _get(port, "/api/forecast")
        assert status == 200
        assert "projected_total" in body
    finally:
        server.shutdown()


def test_serve_status_endpoint(tmp_path, monkeypatch, db_path):
    """GET /api/status should return 200 with project info."""
    monkeypatch.chdir(tmp_path)
    create_project(
        name="serve-status",
        path=str(tmp_path),
        baseline_daily_cost=5.0,
        baseline_total_days=7,
        baseline_total_cost=35.0,
    )

    port = _free_port()
    server = _start_server(port)
    try:
        status, body, _ = _get(port, "/api/status")
        assert status == 200
        assert "project" in body
        assert body["project"]["name"] == "serve-status"
    finally:
        server.shutdown()


def test_serve_costs_endpoint(tmp_path, monkeypatch, db_path):
    """GET /api/costs should return 200 with logs."""
    monkeypatch.chdir(tmp_path)
    project_id = create_project(
        name="serve-costs",
        path=str(tmp_path),
        baseline_daily_cost=5.0,
        baseline_total_days=7,
        baseline_total_cost=35.0,
    )
    conn = get_or_create_db()
    ts = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO usage_logs (project_id, timestamp, model, provider, "
        "tokens_in, tokens_out, cost_usd, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (project_id, ts, "gpt-4o-mini", "openai", 100, 50, 0.001, None),
    )
    conn.commit()

    port = _free_port()
    server = _start_server(port)
    try:
        status, body, _ = _get(port, "/api/costs")
        assert status == 200
        assert "logs" in body
        assert len(body["logs"]) >= 1
    finally:
        server.shutdown()


def test_serve_cors_headers(tmp_path, monkeypatch, db_path):
    """Responses should include Access-Control-Allow-Origin: *."""
    monkeypatch.chdir(tmp_path)
    port = _free_port()
    server = _start_server(port)
    try:
        _, _, headers = _get(port, "/api/health")
        assert headers.get("Access-Control-Allow-Origin") == "*"
    finally:
        server.shutdown()


def test_serve_404(tmp_path, monkeypatch, db_path):
    """Unknown paths should return 404."""
    monkeypatch.chdir(tmp_path)
    create_project(
        name="serve-404",
        path=str(tmp_path),
        baseline_daily_cost=5.0,
        baseline_total_days=7,
        baseline_total_cost=35.0,
    )
    port = _free_port()
    server = _start_server(port)
    try:
        status, body, _ = _get(port, "/api/nonexistent")
        assert status == 404
        assert "error" in body
    finally:
        server.shutdown()
