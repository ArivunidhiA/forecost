"""
End-to-end integration smoke test.

Exercises the full system flow without external APIs:
  create user → store key → create budget → create webhook → create tags →
  proxy request (mocked) with auto-tagging → verify log → verify stats →
  export CSV → forecast → anomalies

All external calls (LLM providers) are mocked. This validates that all
components work together as an integrated system.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_response(json_data):
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {"content-type": "application/json"}
    resp.json.return_value = json_data
    resp.content = json.dumps(json_data).encode()
    return resp


OPENAI_RESPONSE = {
    "id": "chatcmpl-integration",
    "model": "gpt-4o",
    "choices": [{"message": {"content": "Integration test!"}}],
    "usage": {"prompt_tokens": 50, "completion_tokens": 25},
}


class TestFullIntegrationFlow:
    """Single end-to-end test that exercises the entire system."""

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_complete_flow(self, mock_proxy, client, db_session, auth_headers, test_user):
        """Full flow: key → budget → webhook → tags → proxy → logs → stats → export → forecast → anomalies."""
        mock_proxy.return_value = _make_mock_response(OPENAI_RESPONSE)

        # ------------------------------------------------------------------
        # 1. Store API key
        # ------------------------------------------------------------------
        key_resp = client.post(
            "/api/v1/keys",
            json={"provider": "openai", "api_key": "sk-integration-test-key-12345"},
            headers=auth_headers,
        )
        assert key_resp.status_code == 200
        proxy_key = key_resp.json()["proxy_key"]
        assert proxy_key.startswith("llmlab_pk_")

        # ------------------------------------------------------------------
        # 2. Create budget
        # ------------------------------------------------------------------
        budget_resp = client.post(
            "/api/v1/budgets",
            json={"amount_usd": 50.0, "alert_threshold": 80.0},
            headers=auth_headers,
        )
        assert budget_resp.status_code == 200
        assert budget_resp.json()["amount_usd"] == 50.0

        # ------------------------------------------------------------------
        # 3. Register webhook
        # ------------------------------------------------------------------
        webhook_resp = client.post(
            "/api/v1/webhooks",
            json={"url": "https://hooks.example.com/llmlab", "event_type": "budget_warning"},
            headers=auth_headers,
        )
        assert webhook_resp.status_code == 200

        # ------------------------------------------------------------------
        # 4. Create tags
        # ------------------------------------------------------------------
        tag_resp = client.post(
            "/api/v1/tags",
            json={"name": "integration-test", "color": "#ff0000"},
            headers=auth_headers,
        )
        assert tag_resp.status_code == 200
        tag_id = tag_resp.json()["id"]

        # ------------------------------------------------------------------
        # 5. Proxy a request with X-LLMLab-Tags header
        # ------------------------------------------------------------------
        proxy_resp = client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {proxy_key}",
                "X-LLMLab-Tags": "integration-test,auto-created-tag",
            },
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]},
        )
        assert proxy_resp.status_code == 200
        assert proxy_resp.json()["model"] == "gpt-4o"

        # ------------------------------------------------------------------
        # 6. Verify log was created
        # ------------------------------------------------------------------
        logs_resp = client.get("/api/v1/logs", headers=auth_headers)
        assert logs_resp.status_code == 200
        logs_data = logs_resp.json()
        assert logs_data["total"] >= 1

        log = logs_data["logs"][0]
        assert log["provider"] == "openai"
        assert log["model"] == "gpt-4o"
        assert log["input_tokens"] == 50
        assert log["output_tokens"] == 25

        # ------------------------------------------------------------------
        # 7. Verify tags were attached to log
        # ------------------------------------------------------------------
        assert "integration-test" in log["tags"]
        assert "auto-created-tag" in log["tags"]

        # ------------------------------------------------------------------
        # 8. Verify stats are updated
        # ------------------------------------------------------------------
        stats_resp = client.get("/api/v1/stats?period=all", headers=auth_headers)
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["total_calls"] >= 1
        assert stats["total_usd"] > 0
        assert stats["total_tokens"] > 0

        # ------------------------------------------------------------------
        # 9. Verify stats with tag filter
        # ------------------------------------------------------------------
        filtered_stats = client.get(
            "/api/v1/stats?period=all&tag=integration-test", headers=auth_headers
        )
        assert filtered_stats.status_code == 200
        assert filtered_stats.json()["total_calls"] >= 1

        # ------------------------------------------------------------------
        # 10. Export CSV
        # ------------------------------------------------------------------
        csv_resp = client.get("/api/v1/export/csv", headers=auth_headers)
        assert csv_resp.status_code == 200
        assert "text/csv" in csv_resp.headers["content-type"]
        csv_content = csv_resp.text
        assert "gpt-4o" in csv_content
        assert "integration-test" in csv_content

        # ------------------------------------------------------------------
        # 11. Export JSON
        # ------------------------------------------------------------------
        json_resp = client.get("/api/v1/export/json", headers=auth_headers)
        assert json_resp.status_code == 200
        json_data = json.loads(json_resp.text)
        assert json_data["total_logs"] >= 1

        # ------------------------------------------------------------------
        # 12. Forecast (may return zeros with only 1 data point)
        # ------------------------------------------------------------------
        forecast_resp = client.get("/api/v1/stats/forecast", headers=auth_headers)
        assert forecast_resp.status_code == 200
        assert "predicted_next_month_usd" in forecast_resp.json()

        # ------------------------------------------------------------------
        # 13. Anomalies (may be empty with limited data)
        # ------------------------------------------------------------------
        anomaly_resp = client.get("/api/v1/stats/anomalies", headers=auth_headers)
        assert anomaly_resp.status_code == 200
        assert "anomalies" in anomaly_resp.json()

        # ------------------------------------------------------------------
        # 14. Verify all tags exist (both pre-created and auto-created)
        # ------------------------------------------------------------------
        tags_resp = client.get("/api/v1/tags", headers=auth_headers)
        assert tags_resp.status_code == 200
        tag_names = [t["name"] for t in tags_resp.json()["tags"]]
        assert "integration-test" in tag_names
        assert "auto-created-tag" in tag_names

        # ------------------------------------------------------------------
        # 15. Cache stats accessible
        # ------------------------------------------------------------------
        cache_resp = client.get("/api/v1/cache/stats", headers=auth_headers)
        assert cache_resp.status_code == 200

        # ------------------------------------------------------------------
        # 16. Health check
        # ------------------------------------------------------------------
        health_resp = client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json()["status"] in ("healthy", "degraded")
