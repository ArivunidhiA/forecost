import httpx
import pytest

from forecost import db, interceptor


@pytest.fixture
def captured_usage():
    captured = []

    def on_usage(**kwargs):
        captured.append(kwargs)

    return captured, on_usage


@pytest.fixture
def project_id(db_path):
    return db.create_project(
        name="sdk_compat",
        path=str(db_path),
        baseline_daily_cost=0.0,
        baseline_total_days=1,
        baseline_total_cost=0.0,
    )


def test_openai_chat_completion_tracked(db_path, project_id, captured_usage):
    captured, on_usage = captured_usage
    body = {
        "id": "chatcmpl-123",
        "model": "gpt-4o-2024-08-06",
        "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 25},
    }

    def handler(request):
        return httpx.Response(200, json=body)

    interceptor.install(on_usage=on_usage)
    try:
        interceptor.set_project_id(project_id)
        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        client.get("https://api.openai.com/v1/chat/completions")
        assert len(captured) == 1
        assert captured[0]["model"] == "gpt-4o-2024-08-06"
        assert captured[0]["tokens_in"] == 50
        assert captured[0]["tokens_out"] == 25
        assert captured[0]["cost"] > 0
    finally:
        interceptor.uninstall()


def test_anthropic_message_tracked(db_path, project_id, captured_usage):
    captured, on_usage = captured_usage
    body = {
        "id": "msg-123",
        "model": "claude-3-5-sonnet-20241022",
        "content": [{"type": "text", "text": "Hello"}],
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }

    def handler(request):
        return httpx.Response(200, json=body)

    interceptor.install(on_usage=on_usage)
    try:
        interceptor.set_project_id(project_id)
        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        client.post("https://api.anthropic.com/v1/messages")
        assert len(captured) == 1
        assert captured[0]["model"] == "claude-3-5-sonnet-20241022"
        assert captured[0]["tokens_in"] == 100
        assert captured[0]["tokens_out"] == 50
        assert captured[0]["cost"] > 0
    finally:
        interceptor.uninstall()


def test_openai_embedding_tracked(db_path, project_id, captured_usage):
    captured, on_usage = captured_usage
    body = {
        "object": "list",
        "data": [{"embedding": [0.1] * 1536, "index": 0}],
        "model": "text-embedding-3-small",
        "usage": {"prompt_tokens": 200, "total_tokens": 200, "completion_tokens": 0},
    }

    def handler(request):
        return httpx.Response(200, json=body)

    interceptor.install(on_usage=on_usage)
    try:
        interceptor.set_project_id(project_id)
        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        client.post("https://api.openai.com/v1/embeddings")
        assert len(captured) == 1
        assert captured[0]["model"] == "text-embedding-3-small"
        assert captured[0]["tokens_in"] == 200
        assert captured[0]["tokens_out"] == 0
        assert captured[0]["cost"] > 0
    finally:
        interceptor.uninstall()


def test_malformed_response_does_not_crash(db_path, project_id, captured_usage):
    captured, on_usage = captured_usage
    body = {"error": {"message": "Rate limit exceeded"}}

    def handler(request):
        return httpx.Response(429, json=body)

    interceptor.install(on_usage=on_usage)
    try:
        interceptor.set_project_id(project_id)
        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        client.get("https://api.openai.com/v1/chat/completions")
        assert len(captured) == 0
    finally:
        interceptor.uninstall()


def test_non_llm_request_ignored(db_path, project_id, captured_usage):
    captured, on_usage = captured_usage
    body = {"results": [1, 2, 3]}

    def handler(request):
        return httpx.Response(200, json=body)

    interceptor.install(on_usage=on_usage)
    try:
        interceptor.set_project_id(project_id)
        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        client.get("https://example.com/api/data")
        assert len(captured) == 0
    finally:
        interceptor.uninstall()


def test_interceptor_disabled_via_env_var(monkeypatch):
    import httpx

    interceptor.uninstall()
    monkeypatch.setenv("FORECOST_DISABLED", "1")
    original_send = httpx.Client.send
    interceptor.install()
    assert httpx.Client.send is original_send
    interceptor.uninstall()


@pytest.mark.asyncio
async def test_async_interceptor_tracks_usage(db_path, project_id, captured_usage):
    captured, on_usage = captured_usage
    body = {
        "id": "chatcmpl-async-123",
        "model": "gpt-4o",
        "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
        "usage": {"prompt_tokens": 30, "completion_tokens": 10},
    }

    async def handler(request):
        return httpx.Response(200, json=body)

    interceptor.install(on_usage=on_usage)
    try:
        interceptor.set_project_id(project_id)
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await client.get("https://api.openai.com/v1/chat/completions")
        assert len(captured) == 1
        assert captured[0]["model"] == "gpt-4o"
        assert captured[0]["tokens_in"] == 30
    finally:
        interceptor.uninstall()


def test_streaming_response_passes_through(db_path, project_id, captured_usage):
    captured, on_usage = captured_usage
    body = 'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'

    def handler(request):
        return httpx.Response(
            200,
            content=body.encode(),
            headers={"content-type": "text/event-stream"},
        )

    interceptor.install(on_usage=on_usage)
    try:
        interceptor.set_project_id(project_id)
        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        resp = client.get("https://api.openai.com/v1/chat/completions")
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        assert len(captured) == 0
    finally:
        interceptor.uninstall()
