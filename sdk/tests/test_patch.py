"""
Tests for the LLMLab SDK monkey-patching module.
"""

import types
from unittest.mock import MagicMock

import pytest

import sys
import os

# Add sdk directory to path so we can import the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from patch import _get_module_name, _patch_openai, _patch_anthropic, patch, unpatch, DEFAULT_BASE_URL


class TestGetModuleName:
    def test_with_module(self):
        """Should return __name__ for a module."""
        mod = types.ModuleType("openai")
        assert _get_module_name(mod) == "openai"

    def test_with_nested_module(self):
        """Should handle dotted module names."""
        mod = types.ModuleType("google.generativeai")
        assert _get_module_name(mod) == "google.generativeai"

    def test_with_class(self):
        """Should return module name for a class."""

        class FakeClient:
            pass

        FakeClient.__module__ = "anthropic"
        assert "anthropic" in _get_module_name(FakeClient)

    def test_with_empty(self):
        """Should return empty string for objects without name."""
        obj = object()
        result = _get_module_name(obj)
        assert isinstance(result, str)


class TestPatchOpenAI:
    def test_patches_openai_init(self):
        """Should override OpenAI.__init__ to inject proxy settings."""
        # Create a mock openai module
        mock_module = types.ModuleType("openai")

        class MockOpenAI:
            def __init__(self, **kwargs):
                self.base_url = kwargs.get("base_url")
                self.api_key = kwargs.get("api_key")

        mock_module.OpenAI = MockOpenAI

        # Patch it
        _patch_openai(mock_module, "llmlab_pk_test123", "https://proxy.test.com")

        # Now create a client — should have proxy settings
        client = mock_module.OpenAI()
        assert client.base_url == "https://proxy.test.com/api/v1/proxy/openai/v1"
        assert client.api_key == "llmlab_pk_test123"

    def test_patches_async_openai(self):
        """Should also patch AsyncOpenAI if present."""
        mock_module = types.ModuleType("openai")

        class MockOpenAI:
            def __init__(self, **kwargs):
                self.base_url = kwargs.get("base_url")
                self.api_key = kwargs.get("api_key")

        class MockAsyncOpenAI:
            def __init__(self, **kwargs):
                self.base_url = kwargs.get("base_url")
                self.api_key = kwargs.get("api_key")

        mock_module.OpenAI = MockOpenAI
        mock_module.AsyncOpenAI = MockAsyncOpenAI

        _patch_openai(mock_module, "llmlab_pk_test456", DEFAULT_BASE_URL)

        async_client = mock_module.AsyncOpenAI()
        assert async_client.api_key == "llmlab_pk_test456"


class TestPatchAnthropic:
    def test_patches_anthropic_init(self):
        """Should override Anthropic.__init__ to inject proxy settings."""
        mock_module = types.ModuleType("anthropic")

        class MockAnthropic:
            def __init__(self, **kwargs):
                self.base_url = kwargs.get("base_url")
                self.api_key = kwargs.get("api_key")

        mock_module.Anthropic = MockAnthropic

        _patch_anthropic(mock_module, "llmlab_pk_test789", "https://proxy.test.com")

        client = mock_module.Anthropic()
        assert client.base_url == "https://proxy.test.com/api/v1/proxy/anthropic"
        assert client.api_key == "llmlab_pk_test789"


class TestPatch:
    def test_raises_for_unsupported_target(self):
        """Should raise ValueError for unsupported libraries."""
        mock_module = types.ModuleType("unsupported_library")

        with pytest.raises(ValueError, match="Unsupported target"):
            patch(mock_module, proxy_key="llmlab_pk_test")

    def test_detects_openai(self):
        """Should route to _patch_openai for openai module."""
        mock_module = types.ModuleType("openai")
        mock_module.OpenAI = type("OpenAI", (), {"__init__": lambda self, **kw: None})

        # Should not raise
        patch(mock_module, proxy_key="llmlab_pk_test")

    def test_detects_anthropic(self):
        """Should route to _patch_anthropic for anthropic module."""
        mock_module = types.ModuleType("anthropic")
        mock_module.Anthropic = type("Anthropic", (), {"__init__": lambda self, **kw: None})

        # Should not raise
        patch(mock_module, proxy_key="llmlab_pk_test")

    def test_detects_google(self):
        """Should route to _patch_google for google.generativeai module."""
        mock_module = types.ModuleType("google.generativeai")

        # Should not raise
        patch(mock_module, proxy_key="llmlab_pk_test")


class TestTagSupport:
    """Tests for SDK tag support (set_tags, clear_tags, default_headers)."""

    def test_patch_with_tags_sets_current_tags(self):
        """patch(..., tags=["backend"]) should set _current_tags."""
        from patch import _current_tags, set_tags, clear_tags, get_tags

        clear_tags()
        assert get_tags() == []

        mock_module = types.ModuleType("openai")
        mock_module.OpenAI = type("OpenAI", (), {"__init__": lambda self, **kw: None})

        patch(mock_module, proxy_key="llmlab_pk_test", tags=["backend", "prod"])
        assert get_tags() == ["backend", "prod"]

        # Cleanup
        clear_tags()

    def test_set_tags_and_clear_tags(self):
        """set_tags and clear_tags should update module-level state."""
        from patch import set_tags, clear_tags, get_tags

        set_tags(["alpha", "beta"])
        assert get_tags() == ["alpha", "beta"]

        clear_tags()
        assert get_tags() == []

    def test_openai_client_gets_tag_header(self):
        """Patched OpenAI client should have X-LLMLab-Tags in default_headers."""
        from patch import set_tags, clear_tags

        set_tags(["backend", "prod"])

        mock_module = types.ModuleType("openai")

        class MockOpenAI:
            def __init__(self, **kwargs):
                self.base_url = kwargs.get("base_url")
                self.api_key = kwargs.get("api_key")
                self.default_headers = kwargs.get("default_headers", {})

        mock_module.OpenAI = MockOpenAI

        _patch_openai(mock_module, "llmlab_pk_test", "https://proxy.test.com")
        client = mock_module.OpenAI()

        assert client.default_headers.get("X-LLMLab-Tags") == "backend,prod"

        # Cleanup
        clear_tags()

    def test_anthropic_client_gets_tag_header(self):
        """Patched Anthropic client should have X-LLMLab-Tags in default_headers."""
        from patch import set_tags, clear_tags

        set_tags(["staging"])

        mock_module = types.ModuleType("anthropic")

        class MockAnthropic:
            def __init__(self, **kwargs):
                self.base_url = kwargs.get("base_url")
                self.api_key = kwargs.get("api_key")
                self.default_headers = kwargs.get("default_headers", {})

        mock_module.Anthropic = MockAnthropic

        _patch_anthropic(mock_module, "llmlab_pk_test", "https://proxy.test.com")
        client = mock_module.Anthropic()

        assert client.default_headers.get("X-LLMLab-Tags") == "staging"

        # Cleanup
        clear_tags()

    def test_no_tags_no_header(self):
        """Without tags, default_headers should not include X-LLMLab-Tags."""
        from patch import clear_tags

        clear_tags()

        mock_module = types.ModuleType("openai")

        class MockOpenAI:
            def __init__(self, **kwargs):
                self.default_headers = kwargs.get("default_headers", {})

        mock_module.OpenAI = MockOpenAI

        _patch_openai(mock_module, "llmlab_pk_test", "https://proxy.test.com")
        client = mock_module.OpenAI()

        assert "X-LLMLab-Tags" not in client.default_headers


class TestUnpatch:
    def test_unpatch_noop_on_unpatched(self):
        """unpatch() should not raise on an unpatched module."""
        mock_module = types.ModuleType("openai")
        # Should not raise
        unpatch(mock_module)
