"""
Response cache for LLMLab proxy endpoints.

Provides exact-match caching with TTL expiration and LRU eviction.
Supports two backends:
- MemoryCache: In-process OrderedDict (default, no dependencies)
- RedisCache: Persistent Redis cache (requires REDIS_URL)

Cache key = SHA-256 of (provider + request body).
"""

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Optional, Protocol, Tuple, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# CACHE BACKEND PROTOCOL
# =============================================================================


@runtime_checkable
class CacheBackend(Protocol):
    """Protocol defining the cache interface."""

    def get(self, provider: str, body: bytes) -> Optional[Tuple[bytes, dict]]: ...
    def set(self, provider: str, body: bytes, response_body: bytes,
            metadata: dict, ttl: Optional[int] = None) -> None: ...
    def clear(self) -> None: ...
    def stats(self) -> dict: ...


def _make_key(provider: str, body: bytes) -> str:
    """Generate a deterministic cache key from provider + request body."""
    return hashlib.sha256(f"{provider}:{body.hex()}".encode()).hexdigest()


# =============================================================================
# IN-MEMORY CACHE (DEFAULT)
# =============================================================================


class MemoryCache:
    """
    LRU + TTL in-memory response cache.

    Stores provider responses keyed by SHA-256(provider:body).
    Evicts least-recently-used entries when max_size is exceeded.
    Entries expire after TTL seconds.
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.hits = 0
        self.misses = 0

    def _is_expired(self, entry: dict) -> bool:
        """Check if a cache entry has expired."""
        return time.time() > entry["expires_at"]

    def get(self, provider: str, body: bytes) -> Optional[Tuple[bytes, dict]]:
        """
        Look up a cached response.

        Returns:
            Tuple of (response_body, metadata) on hit, or None on miss.
        """
        key = _make_key(provider, body)
        entry = self._cache.get(key)

        if entry is None:
            self.misses += 1
            return None

        if self._is_expired(entry):
            del self._cache[key]
            self.misses += 1
            return None

        self._cache.move_to_end(key)
        self.hits += 1
        return (entry["response_body"], entry["metadata"])

    def set(
        self,
        provider: str,
        body: bytes,
        response_body: bytes,
        metadata: dict,
        ttl: Optional[int] = None,
    ) -> None:
        """Store a response in the cache."""
        key = _make_key(provider, body)
        actual_ttl = ttl if ttl is not None else self.default_ttl

        if key in self._cache:
            del self._cache[key]

        while len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)

        self._cache[key] = {
            "response_body": response_body,
            "metadata": metadata,
            "expires_at": time.time() + actual_ttl,
            "created_at": time.time(),
        }

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self.hits = 0
        self.misses = 0

    def stats(self) -> dict:
        """Return cache statistics."""
        total = self.hits + self.misses
        return {
            "hit_rate": round(self.hits / total, 4) if total > 0 else 0.0,
            "total_hits": self.hits,
            "total_misses": self.misses,
            "size": len(self._cache),
            "max_size": self.max_size,
        }


# =============================================================================
# REDIS CACHE
# =============================================================================


class RedisCache:
    """
    Redis-backed response cache with TTL.

    Uses Redis for persistent caching across server restarts.
    Falls back gracefully if Redis is unavailable.
    """

    def __init__(self, redis_url: str, max_size: int = 10000, default_ttl: int = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.hits = 0
        self.misses = 0
        self._prefix = "llmlab:cache:"
        self._redis = None

        try:
            import redis
            self._redis = redis.from_url(redis_url, decode_responses=False)
            self._redis.ping()
            logger.info(f"Redis cache connected: {redis_url}")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}), falling back to memory cache")
            self._redis = None

    def _redis_key(self, cache_key: str) -> str:
        return f"{self._prefix}{cache_key}"

    def get(self, provider: str, body: bytes) -> Optional[Tuple[bytes, dict]]:
        """Look up a cached response in Redis."""
        if self._redis is None:
            self.misses += 1
            return None

        try:
            key = _make_key(provider, body)
            data = self._redis.get(self._redis_key(key))
            if data is None:
                self.misses += 1
                return None

            entry = json.loads(data)
            response_body = bytes.fromhex(entry["response_body_hex"])
            metadata = entry["metadata"]
            self.hits += 1
            return (response_body, metadata)
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
            self.misses += 1
            return None

    def set(
        self,
        provider: str,
        body: bytes,
        response_body: bytes,
        metadata: dict,
        ttl: Optional[int] = None,
    ) -> None:
        """Store a response in Redis with TTL."""
        if self._redis is None:
            return

        try:
            key = _make_key(provider, body)
            actual_ttl = ttl if ttl is not None else self.default_ttl
            entry = {
                "response_body_hex": response_body.hex(),
                "metadata": metadata,
            }
            self._redis.setex(
                self._redis_key(key),
                actual_ttl,
                json.dumps(entry),
            )
        except Exception as e:
            logger.warning(f"Redis set error: {e}")

    def clear(self) -> None:
        """Clear all cached entries."""
        if self._redis is None:
            return
        try:
            keys = self._redis.keys(f"{self._prefix}*")
            if keys:
                self._redis.delete(*keys)
            self.hits = 0
            self.misses = 0
        except Exception as e:
            logger.warning(f"Redis clear error: {e}")

    def stats(self) -> dict:
        """Return cache statistics."""
        total = self.hits + self.misses
        size = 0
        if self._redis:
            try:
                size = len(self._redis.keys(f"{self._prefix}*"))
            except Exception:
                pass

        return {
            "hit_rate": round(self.hits / total, 4) if total > 0 else 0.0,
            "total_hits": self.hits,
            "total_misses": self.misses,
            "size": size,
            "max_size": self.max_size,
        }


# =============================================================================
# BACKWARD COMPATIBILITY ALIAS
# =============================================================================

# Keep ResponseCache as an alias for MemoryCache so existing tests work
ResponseCache = MemoryCache


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================


def _create_cache() -> CacheBackend:
    """Auto-detect cache backend based on REDIS_URL env var."""
    import os
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        cache = RedisCache(redis_url=redis_url, max_size=10000, default_ttl=3600)
        if cache._redis is not None:
            return cache
        logger.info("Redis not available, using in-memory cache")
    return MemoryCache(max_size=1000, default_ttl=3600)


response_cache = _create_cache()
