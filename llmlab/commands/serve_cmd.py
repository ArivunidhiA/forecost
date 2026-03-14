import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import click

from llmlab.db import get_active_days, get_daily_costs, get_project_by_path, get_recent_usage_logs
from llmlab.forecaster import ProjectForecaster

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def _project_or_error():
    path = os.path.abspath(os.getcwd())
    project = get_project_by_path(path)
    if project is None:
        return None, {"error": "No project found for current directory", "path": path}
    return project, None


def _send_json(handler, data, status=200):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    for k, v in CORS_HEADERS.items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


def _send_404(handler):
    handler.send_response(404)
    handler.send_header("Content-Type", "application/json")
    for k, v in CORS_HEADERS.items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(json.dumps({"error": "Not found"}).encode())


class LLMLabHandler(BaseHTTPRequestHandler):
    def _send_cors_preflight(self):
        self.send_response(204)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_OPTIONS(self):
        self._send_cors_preflight()

    def do_GET(self):
        if self.path == "/api/health":
            _send_json(self, {"status": "ok"})
            return

        project, err = _project_or_error()
        if err is not None:
            if self.path in ("/api/forecast", "/api/status", "/api/costs"):
                _send_json(self, err, 404)
                return
            _send_404(self)
            return

        if self.path == "/api/forecast":
            try:
                forecaster = ProjectForecaster(project["id"])
                result = forecaster.calculate_forecast(save=False)
                _send_json(self, result)
            except Exception as e:
                _send_json(self, {"error": str(e)}, 500)
            return

        if self.path == "/api/status":
            active_days = get_active_days(project["id"])
            daily_costs = get_daily_costs(project["id"])
            actual_spend = sum(c for _, c in daily_costs)
            out = {
                "project": {
                    "id": project["id"],
                    "name": project["name"],
                    "path": project["path"],
                    "baseline_daily_cost": project["baseline_daily_cost"],
                    "baseline_total_days": project["baseline_total_days"],
                    "baseline_total_cost": project["baseline_total_cost"],
                },
                "active_days": active_days,
                "actual_spend": actual_spend,
            }
            _send_json(self, out)
            return

        if self.path == "/api/costs":
            logs = get_recent_usage_logs(project["id"])
            _send_json(self, {"logs": logs})
            return

        _send_404(self)

    def log_message(self, format, *args):
        pass


@click.command()
@click.option("--port", default=8787, help="Port to listen on")
def serve(port):
    """Start a local API server for programmatic access."""
    server = HTTPServer(("127.0.0.1", port), LLMLabHandler)
    print(f"llmlab server running on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
