import pytest

from llmcast import interceptor


@pytest.fixture(autouse=True)
def ensure_uninstalled():
    interceptor.uninstall()
    yield
    interceptor.uninstall()


def test_install_uninstall_patches_httpx():
    import httpx

    original_send = httpx.Client.send
    original_async_send = httpx.AsyncClient.send
    interceptor.install()
    assert httpx.Client.send is not original_send
    assert httpx.AsyncClient.send is not original_async_send
    interceptor.uninstall()
    assert httpx.Client.send is original_send
    assert httpx.AsyncClient.send is original_async_send


def test_patching_does_not_break_normal_requests():
    import httpx

    def fake_handler(request):
        return httpx.Response(200, json={"usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    interceptor.install()
    try:
        transport = httpx.MockTransport(fake_handler)
        client = httpx.Client(transport=transport)
        resp = client.get("https://example.com/")
        assert resp.status_code == 200
    finally:
        interceptor.uninstall()
