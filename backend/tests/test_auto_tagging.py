"""
Tests for the X-LLMLab-Tags auto-tagging feature.

Verifies that proxy calls with X-LLMLab-Tags header automatically create
and attach tags to the resulting UsageLog entries.
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
    "model": "gpt-4o",
    "choices": [{"message": {"content": "Tagged!"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}


class TestAutoTagSingleTag:
    """Test auto-tagging with a single tag."""

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_single_tag_created_and_attached(self, mock_proxy, client, db_session, test_openai_key):
        """X-LLMLab-Tags: backend should create tag and attach it to the log."""
        mock_proxy.return_value = _make_mock_response(OPENAI_RESPONSE)

        client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {test_openai_key.proxy_key}",
                "X-LLMLab-Tags": "backend",
            },
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
        )

        from models import Tag, UsageLog
        tags = db_session.query(Tag).filter(
            Tag.user_id == test_openai_key.user_id, Tag.name == "backend"
        ).all()
        assert len(tags) == 1

        logs = db_session.query(UsageLog).filter(
            UsageLog.user_id == test_openai_key.user_id
        ).all()
        assert len(logs) == 1
        assert "backend" in [t.name for t in logs[0].tags]


class TestAutoTagMultipleTags:
    """Test auto-tagging with multiple comma-separated tags."""

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_multiple_tags_created(self, mock_proxy, client, db_session, test_openai_key):
        """X-LLMLab-Tags: backend,production,feature-x should create all 3 tags."""
        mock_proxy.return_value = _make_mock_response(OPENAI_RESPONSE)

        client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {test_openai_key.proxy_key}",
                "X-LLMLab-Tags": "backend,production,feature-x",
            },
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
        )

        from models import Tag, UsageLog
        tags = db_session.query(Tag).filter(Tag.user_id == test_openai_key.user_id).all()
        tag_names = {t.name for t in tags}
        assert "backend" in tag_names
        assert "production" in tag_names
        assert "feature-x" in tag_names

        logs = db_session.query(UsageLog).filter(UsageLog.user_id == test_openai_key.user_id).all()
        assert len(logs[0].tags) == 3


class TestAutoTagExistingTags:
    """Test that existing tags are reused, not duplicated."""

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_existing_tag_reused(self, mock_proxy, client, db_session, test_openai_key, test_tags):
        """Pre-existing tag should be reused, not duplicated."""
        mock_proxy.return_value = _make_mock_response(OPENAI_RESPONSE)

        # "backend" tag already exists from test_tags fixture
        client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {test_openai_key.proxy_key}",
                "X-LLMLab-Tags": "backend",
            },
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
        )

        from models import Tag
        backend_tags = db_session.query(Tag).filter(
            Tag.user_id == test_openai_key.user_id, Tag.name == "backend"
        ).all()
        # Should be exactly 1 — not duplicated
        assert len(backend_tags) == 1


class TestAutoTagEdgeCases:
    """Test edge cases for auto-tagging."""

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_empty_header_no_tags(self, mock_proxy, client, db_session, test_openai_key):
        """Empty X-LLMLab-Tags header should not create any tags."""
        mock_proxy.return_value = _make_mock_response(OPENAI_RESPONSE)

        client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {test_openai_key.proxy_key}",
                "X-LLMLab-Tags": "",
            },
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
        )

        from models import UsageLog
        logs = db_session.query(UsageLog).filter(UsageLog.user_id == test_openai_key.user_id).all()
        assert len(logs) == 1
        assert len(logs[0].tags) == 0

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_no_header_no_tags(self, mock_proxy, client, db_session, test_openai_key):
        """No X-LLMLab-Tags header should not create any tags."""
        mock_proxy.return_value = _make_mock_response(OPENAI_RESPONSE)

        client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {test_openai_key.proxy_key}"},
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
        )

        from models import UsageLog
        logs = db_session.query(UsageLog).filter(UsageLog.user_id == test_openai_key.user_id).all()
        assert len(logs) == 1
        assert len(logs[0].tags) == 0

    @patch("main.OpenAIProvider.proxy_request", new_callable=AsyncMock)
    def test_whitespace_tags_ignored(self, mock_proxy, client, db_session, test_openai_key):
        """Tags with whitespace should be trimmed; empty entries ignored."""
        mock_proxy.return_value = _make_mock_response(OPENAI_RESPONSE)

        client.post(
            "/api/v1/proxy/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {test_openai_key.proxy_key}",
                "X-LLMLab-Tags": "backend, , production",
            },
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
        )

        from models import UsageLog
        logs = db_session.query(UsageLog).filter(UsageLog.user_id == test_openai_key.user_id).all()
        tag_names = [t.name for t in logs[0].tags]
        assert "backend" in tag_names
        assert "production" in tag_names
        assert len(tag_names) == 2  # Empty entry should be ignored
