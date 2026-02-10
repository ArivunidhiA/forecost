"""
Tests for proxy endpoints (OpenAI, Anthropic, Google).

External provider APIs are mocked — we test the proxy routing, auth,
usage logging, latency tracking, and error handling.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers to build mock httpx.Response objects
# ---------------------------------------------------------------------------

def _make_mock_response(status_code=200, json_data=None, content=None, headers=None):
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {"content-type": "application/json"}
    if json_data is not None:
        resp.json.return_value = json_data
        resp.content = json.dumps(json_data).encode()
    elif content is not None:
        resp.content = content
    else:
        resp.content = b"{}"
    return resp


OPENAI_RESPONSE = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "model": "gpt-4o",
    "choices": [{"message": {"content": "Hello!"}, "index": 0}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

ANTHROPIC_RESPONSE = {
    "id": "msg-test",
    "type": "message",
    "model": "claude-3-5-sonnet-20241022",
    "content": [{"type": "text", "text": "Hello!"}],
    "usage": {"input_tokens": 20, "output_tokens": 8},
}

GOOGLE_RESPONSE = {
    "candidates": [{"content": {"parts": [{"text": "Hello!"}]}}],
    "usageMetadata": {"promptTokenCount": 15, "candidatesTokenCount": 6, "totalTokenCount": 21},
    "modelVersion": "gemini-1.5-flash",
}


# =============================================================================
# OPENAI PROXY
# =============================================================================


class TestProxyOpenAI:
    """Tests for POST /api/v1/proxy/openai/{path}."""

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_successful_proxy(self, mock_proxy, client, db_session, test_openai_key):
        """Successful OpenAI proxy returns response and creates UsageLog."""
        mock_proxy.return_value = _make_mock_response(json_data=OPENAI_RESPONSE)

        response = client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {test_openai_key.proxy_key}"},
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "gpt-4o"
        mock_proxy.assert_called_once()

        # Verify UsageLog was created
        from models import UsageLog
        logs = db_session.query(UsageLog).filter(UsageLog.user_id == test_openai_key.user_id).all()
        assert len(logs) == 1
        assert logs[0].provider == "openai"
        assert logs[0].model == "gpt-4o"
        assert logs[0].input_tokens == 10
        assert logs[0].output_tokens == 5
        assert logs[0].cost_usd > 0
        assert logs[0].latency_ms >= 0
        assert logs[0].cache_hit is False

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_last_used_at_updated(self, mock_proxy, client, db_session, test_openai_key):
        """Proxy call should update last_used_at on the API key."""
        mock_proxy.return_value = _make_mock_response(json_data=OPENAI_RESPONSE)
        assert test_openai_key.last_used_at is None

        client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {test_openai_key.proxy_key}"},
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
        )

        db_session.refresh(test_openai_key)
        assert test_openai_key.last_used_at is not None

    def test_invalid_proxy_key_returns_401(self, client):
        """Invalid proxy key should return 401."""
        response = client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={"Authorization": "Bearer llmlab_pk_invalid_key"},
            json={"model": "gpt-4o", "messages": []},
        )
        assert response.status_code == 401

    def test_missing_proxy_key_returns_401(self, client):
        """Missing proxy key should return 401."""
        response = client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": []},
        )
        assert response.status_code == 401

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_provider_500_propagated(self, mock_proxy, client, test_openai_key):
        """Provider returning 500 should be propagated to client."""
        mock_proxy.return_value = _make_mock_response(
            status_code=500,
            content=b'{"error": "Internal server error"}',
        )

        response = client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {test_openai_key.proxy_key}"},
            json={"model": "gpt-4o", "messages": []},
        )
        assert response.status_code == 500

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_provider_429_propagated(self, mock_proxy, client, test_openai_key):
        """Provider rate limit (429) should be passed through."""
        mock_proxy.return_value = _make_mock_response(
            status_code=429,
            content=b'{"error": "Rate limited"}',
        )

        response = client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {test_openai_key.proxy_key}"},
            json={"model": "gpt-4o", "messages": []},
        )
        assert response.status_code == 429


# =============================================================================
# ANTHROPIC PROXY
# =============================================================================


class TestProxyAnthropic:
    """Tests for POST /api/v1/proxy/anthropic/{path}."""

    @patch("main.AnthropicProvider.proxy_request", new_callable=AsyncMock)
    def test_successful_proxy(self, mock_proxy, client, db_session, test_anthropic_key):
        """Successful Anthropic proxy returns response and creates UsageLog."""
        mock_proxy.return_value = _make_mock_response(json_data=ANTHROPIC_RESPONSE)

        response = client.post(
            "/api/v1/proxy/anthropic/v1/messages",
            headers={"x-api-key": test_anthropic_key.proxy_key},
            json={"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "Hi"}]},
        )

        assert response.status_code == 200
        mock_proxy.assert_called_once()

        # Verify UsageLog
        from models import UsageLog
        logs = db_session.query(UsageLog).filter(UsageLog.user_id == test_anthropic_key.user_id).all()
        assert len(logs) == 1
        assert logs[0].provider == "anthropic"
        assert logs[0].input_tokens == 20
        assert logs[0].output_tokens == 8

    @patch("main.AnthropicProvider.proxy_request", new_callable=AsyncMock)
    def test_x_api_key_header_extraction(self, mock_proxy, client, test_anthropic_key):
        """Proxy key should be extractable from x-api-key header."""
        mock_proxy.return_value = _make_mock_response(json_data=ANTHROPIC_RESPONSE)

        response = client.post(
            "/api/v1/proxy/anthropic/v1/messages",
            headers={"x-api-key": test_anthropic_key.proxy_key},
            json={"model": "claude-3-5-sonnet-20241022", "messages": []},
        )
        assert response.status_code == 200


# =============================================================================
# GOOGLE PROXY
# =============================================================================


class TestProxyGoogle:
    """Tests for POST /api/v1/proxy/google/{path}."""

    @patch("main.GoogleProvider.proxy_request", new_callable=AsyncMock)
    def test_successful_proxy(self, mock_proxy, client, db_session, test_user):
        """Successful Google proxy returns response and creates UsageLog."""
        from models import ApiKey
        from security import encrypt_api_key

        # Create a Google API key
        google_key = ApiKey(
            user_id=test_user.id,
            provider="google",
            encrypted_key=encrypt_api_key("AIzaSyTestKey123"),
            proxy_key="llmlab_pk_test_google_12345678",
        )
        db_session.add(google_key)
        db_session.commit()

        mock_proxy.return_value = _make_mock_response(json_data=GOOGLE_RESPONSE)

        response = client.post(
            "/api/v1/proxy/google/v1beta/models/gemini-1.5-flash:generateContent",
            headers={"Authorization": f"Bearer {google_key.proxy_key}"},
            json={"contents": [{"parts": [{"text": "Hi"}]}]},
        )

        assert response.status_code == 200
        mock_proxy.assert_called_once()

        # Verify UsageLog
        from models import UsageLog
        logs = db_session.query(UsageLog).filter(UsageLog.user_id == test_user.id).all()
        assert len(logs) == 1
        assert logs[0].provider == "google"
