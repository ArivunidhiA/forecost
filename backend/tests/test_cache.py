"""
Tests for the ResponseCache (LRU + TTL in-process cache).
"""

import time

import pytest

from cache import ResponseCache


class TestResponseCache:
    """Tests for the ResponseCache class."""

    def test_cache_miss(self):
        """get() should return None for unknown key and increment misses."""
        cache = ResponseCache(max_size=10, default_ttl=60)
        result = cache.get("openai", b'{"model": "gpt-4o"}')
        assert result is None
        assert cache.misses == 1
        assert cache.hits == 0

    def test_cache_hit(self):
        """set() then get() should return the cached response and increment hits."""
        cache = ResponseCache(max_size=10, default_ttl=60)
        body = b'{"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}]}'
        response_body = b'{"id": "chatcmpl-123", "choices": [{"message": {"content": "Hi!"}}]}'
        metadata = {"input_tokens": 10, "output_tokens": 5, "model": "gpt-4o", "cost_usd": 0.001}

        cache.set("openai", body, response_body, metadata)
        result = cache.get("openai", body)

        assert result is not None
        cached_body, cached_meta = result
        assert cached_body == response_body
        assert cached_meta == metadata
        assert cache.hits == 1
        assert cache.misses == 0

    def test_ttl_expiration(self):
        """Entries should expire after TTL seconds."""
        cache = ResponseCache(max_size=10, default_ttl=60)
        body = b'{"model": "gpt-4o"}'
        response_body = b'{"response": "ok"}'
        metadata = {"model": "gpt-4o"}

        # Set with very short TTL
        cache.set("openai", body, response_body, metadata, ttl=0)

        # Small sleep to ensure expiration
        time.sleep(0.01)

        result = cache.get("openai", body)
        assert result is None
        assert cache.misses == 1

    def test_lru_eviction(self):
        """Oldest entries should be evicted when cache is full."""
        cache = ResponseCache(max_size=3, default_ttl=60)

        # Fill the cache
        for i in range(3):
            cache.set("openai", f"body-{i}".encode(), f"resp-{i}".encode(), {"i": i})

        assert len(cache._cache) == 3

        # Add one more — should evict body-0
        cache.set("openai", b"body-3", b"resp-3", {"i": 3})
        assert len(cache._cache) == 3

        # body-0 should be evicted
        result = cache.get("openai", b"body-0")
        assert result is None

        # body-1 should still be there
        result = cache.get("openai", b"body-1")
        assert result is not None

    def test_key_deterministic(self):
        """Same (provider, body) should produce the same cache key."""
        cache = ResponseCache()
        key1 = cache._make_key("openai", b"hello world")
        key2 = cache._make_key("openai", b"hello world")
        assert key1 == key2

    def test_key_different_inputs(self):
        """Different inputs should produce different cache keys."""
        cache = ResponseCache()
        key1 = cache._make_key("openai", b"hello")
        key2 = cache._make_key("openai", b"world")
        key3 = cache._make_key("anthropic", b"hello")
        assert key1 != key2
        assert key1 != key3

    def test_clear(self):
        """clear() should empty the cache and reset counters."""
        cache = ResponseCache(max_size=10, default_ttl=60)
        cache.set("openai", b"body", b"resp", {"m": "gpt-4o"})
        cache.get("openai", b"body")  # hit
        cache.get("openai", b"miss")  # miss

        cache.clear()

        assert len(cache._cache) == 0
        assert cache.hits == 0
        assert cache.misses == 0

    def test_stats(self):
        """stats() should return correct hit_rate, counts, and sizes."""
        cache = ResponseCache(max_size=100, default_ttl=60)
        cache.set("openai", b"body", b"resp", {"m": "gpt-4o"})

        # 1 hit, 1 miss
        cache.get("openai", b"body")
        cache.get("openai", b"other")

        stats = cache.stats()
        assert stats["total_hits"] == 1
        assert stats["total_misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["size"] == 1
        assert stats["max_size"] == 100

    def test_stats_empty(self):
        """stats() on empty cache should return zeros."""
        cache = ResponseCache()
        stats = cache.stats()
        assert stats["hit_rate"] == 0.0
        assert stats["total_hits"] == 0
        assert stats["total_misses"] == 0
        assert stats["size"] == 0

    def test_overwrite_existing_key(self):
        """Setting the same key twice should overwrite the value."""
        cache = ResponseCache(max_size=10, default_ttl=60)
        body = b'{"model": "gpt-4o"}'

        cache.set("openai", body, b"response-v1", {"version": 1})
        cache.set("openai", body, b"response-v2", {"version": 2})

        result = cache.get("openai", body)
        assert result is not None
        assert result[0] == b"response-v2"
        assert result[1]["version"] == 2
        assert len(cache._cache) == 1
