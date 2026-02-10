"""
Tests for cache integration with the proxy endpoints.

Verifies cache miss → store → hit lifecycle, streaming bypass, and metadata.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_response(status_code=200, json_data=None, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {"content-type": "application/json"}
    if json_data:
        resp.json.return_value = json_data
        resp.content = json.dumps(json_data).encode()
    else:
        resp.content = b"{}"
    return resp


OPENAI_RESPONSE = {
    "id": "chatcmpl-cache-test",
    "model": "gpt-4o",
    "choices": [{"message": {"content": "Cached!"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}


class TestCacheMissAndHit:
    """Test cache miss on first call, cache hit on second identical call."""

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_first_call_is_cache_miss(self, mock_proxy, client, db_session, test_openai_key):
        """First proxy call should be a cache miss — provider is called."""
        # Clear any existing cache state
        from main import response_cache
        response_cache.clear()

        mock_proxy.return_value = _make_mock_response(json_data=OPENAI_RESPONSE)

        body = {"model": "gpt-4o", "messages": [{"role": "user", "content": "cache test"}]}
        response = client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {test_openai_key.proxy_key}"},
            json=body,
        )

        assert response.status_code == 200
        mock_proxy.assert_called_once()

        # Verify log is NOT a cache hit
        from models import UsageLog
        logs = db_session.query(UsageLog).filter(
            UsageLog.user_id == test_openai_key.user_id
        ).all()
        assert len(logs) == 1
        assert logs[0].cache_hit is False
        assert logs[0].cost_usd > 0

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_second_call_is_cache_hit(self, mock_proxy, client, db_session, test_openai_key):
        """Second identical proxy call should be a cache hit — provider NOT called again."""
        from main import response_cache
        response_cache.clear()

        mock_proxy.return_value = _make_mock_response(json_data=OPENAI_RESPONSE)

        body = {"model": "gpt-4o", "messages": [{"role": "user", "content": "cache test 2"}]}
        headers = {"Authorization": f"Bearer {test_openai_key.proxy_key}"}

        # First call — cache miss
        client.post("/api/v1/proxy/openai/v1/chat/completions", headers=headers, json=body)
        assert mock_proxy.call_count == 1

        # Second identical call — should hit cache
        response2 = client.post("/api/v1/proxy/openai/v1/chat/completions", headers=headers, json=body)
        assert response2.status_code == 200
        # Provider should NOT be called again
        assert mock_proxy.call_count == 1

        # Verify second log is a cache hit
        from models import UsageLog
        logs = db_session.query(UsageLog).filter(
            UsageLog.user_id == test_openai_key.user_id
        ).order_by(UsageLog.created_at).all()
        assert len(logs) == 2
        assert logs[1].cache_hit is True
        assert logs[1].cost_usd == 0.0
        assert logs[1].latency_ms == 0.0


class TestCacheStreamingBypass:
    """Streaming requests should bypass the cache entirely."""

    @patch("main.OpenAIProvider.stream_request")
    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_streaming_bypasses_cache(
        self, mock_proxy, mock_stream, client, db_session, test_openai_key
    ):
        """Streaming requests should not check or store in cache."""
        from main import response_cache
        response_cache.clear()

        # Mock stream to yield chunks
        async def mock_stream_gen(*args, **kwargs):
            yield (200, {"content-type": "text/event-stream"})
            yield b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        mock_stream.return_value = mock_stream_gen()

        body = {"model": "gpt-4o", "messages": [{"role": "user", "content": "stream"}], "stream": True}
        response = client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {test_openai_key.proxy_key}"},
            json=body,
        )

        assert response.status_code == 200
        # proxy_request should NOT have been called (streaming uses stream_request)
        mock_proxy.assert_not_called()

        # Cache should still be empty — streaming doesn't store
        stats = response_cache.stats()
        assert stats.get("hits", 0) == 0
