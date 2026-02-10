"""
LLMLab SDK Monkey-Patching Module

Provides a one-line integration to route any LLM SDK through LLMLab proxy
for automatic cost tracking, caching, and analytics.

Usage:
    import openai
    from llmlab import patch
    patch(openai, proxy_key="llmlab_pk_xxx")

    # All subsequent OpenAI calls now go through LLMLab proxy
    client = openai.OpenAI()
    response = client.chat.completions.create(model="gpt-4o", ...)

Supported libraries:
    - openai (v1+)
    - anthropic (v0.18+)
    - google-generativeai (v0.3+)
"""

from typing import List, Optional

# Default LLMLab proxy base URL
DEFAULT_BASE_URL = "https://api.llmlab.dev"

# Module-level tag state for runtime tag changes
_current_tags: List[str] = []


def set_tags(tags: List[str]) -> None:
    """
    Set the active tags for all subsequent LLM calls.

    Tags are sent as the X-LLMLab-Tags header and used for cost attribution.

    Args:
        tags: List of tag names (e.g., ["backend", "prod"]).

    Example:
        >>> import llmlab
        >>> llmlab.set_tags(["production", "feature-x"])
    """
    global _current_tags
    _current_tags = list(tags)


def clear_tags() -> None:
    """
    Remove all active tags.

    Example:
        >>> import llmlab
        >>> llmlab.clear_tags()
    """
    global _current_tags
    _current_tags = []


def get_tags() -> List[str]:
    """Return the currently active tags."""
    return list(_current_tags)


def patch(
    target,
    proxy_key: str,
    base_url: str = DEFAULT_BASE_URL,
    tags: Optional[List[str]] = None,
) -> None:
    """
    Monkey-patch an LLM SDK to route all requests through LLMLab proxy.

    This transparently intercepts API calls so you get cost tracking,
    caching, and analytics without changing any of your existing code.

    Args:
        target: The LLM library module or client class to patch.
                Supports: openai, anthropic, google.generativeai
        proxy_key: Your LLMLab proxy key (starts with llmlab_pk_).
        base_url: LLMLab API base URL (default: https://api.llmlab.dev).
        tags: Optional list of tags for cost attribution (e.g., ["backend", "prod"]).
              Tags are sent as the X-LLMLab-Tags header.

    Raises:
        ValueError: If the target library is not recognized.

    Example:
        >>> import openai
        >>> from llmlab import patch
        >>> patch(openai, proxy_key="llmlab_pk_abc123", tags=["backend"])
        >>> # Now all OpenAI calls are tracked through LLMLab with tags
    """
    # Set initial tags if provided
    if tags is not None:
        set_tags(tags)

    module_name = _get_module_name(target)

    if "openai" in module_name:
        _patch_openai(target, proxy_key, base_url)
    elif "anthropic" in module_name:
        _patch_anthropic(target, proxy_key, base_url)
    elif "google" in module_name or "genai" in module_name:
        _patch_google(target, proxy_key, base_url)
    else:
        raise ValueError(
            f"Unsupported target: {module_name}. "
            "Supported libraries: openai, anthropic, google-generativeai"
        )


def _get_module_name(target) -> str:
    """Extract the module name from a module or class."""
    import types

    # If it's a module, use __name__
    if isinstance(target, types.ModuleType):
        return getattr(target, "__name__", "").lower()

    # If it's a class, check __module__ first (e.g., "anthropic")
    if isinstance(target, type):
        module = getattr(target, "__module__", "")
        if module:
            return module.lower()
        return getattr(target, "__name__", "").lower()

    # If it's a class instance, use __module__ or the type's __module__
    module = getattr(target, "__module__", "")
    if module:
        return module.lower()

    cls = type(target)
    module = getattr(cls, "__module__", "")
    return module.lower()


# =============================================================================
# OPENAI PATCHING
# =============================================================================


def _build_tag_headers() -> dict:
    """Build the X-LLMLab-Tags header dict from current tags."""
    if _current_tags:
        return {"X-LLMLab-Tags": ",".join(_current_tags)}
    return {}


def _patch_openai(target, proxy_key: str, base_url: str) -> None:
    """
    Patch the OpenAI SDK to route through LLMLab proxy.

    For openai v1+, the SDK uses client instances with base_url and api_key.
    We patch the OpenAI class __init__ to inject our proxy settings and tag headers.
    """
    proxy_url = f"{base_url}/api/v1/proxy/openai/v1"

    # Check if target is the openai module or an OpenAI client class
    openai_module = target
    if hasattr(target, "OpenAI"):
        # It's the module — patch the OpenAI class
        _original_init = target.OpenAI.__init__

        def _patched_init(self, *args, **kwargs):
            # Override base_url and api_key with LLMLab proxy
            kwargs["base_url"] = proxy_url
            kwargs["api_key"] = proxy_key
            # Inject tag headers (read at instantiation time; use set_tags() for runtime changes)
            existing_headers = kwargs.get("default_headers", {}) or {}
            existing_headers.update(_build_tag_headers())
            if existing_headers:
                kwargs["default_headers"] = existing_headers
            _original_init(self, *args, **kwargs)

        target.OpenAI.__init__ = _patched_init

        # Also patch AsyncOpenAI if it exists
        if hasattr(target, "AsyncOpenAI"):
            _original_async_init = target.AsyncOpenAI.__init__

            def _patched_async_init(self, *args, **kwargs):
                kwargs["base_url"] = proxy_url
                kwargs["api_key"] = proxy_key
                existing_headers = kwargs.get("default_headers", {}) or {}
                existing_headers.update(_build_tag_headers())
                if existing_headers:
                    kwargs["default_headers"] = existing_headers
                _original_async_init(self, *args, **kwargs)

            target.AsyncOpenAI.__init__ = _patched_async_init

    # Also set module-level attributes for legacy usage
    if hasattr(openai_module, "api_key"):
        openai_module.api_key = proxy_key
    if hasattr(openai_module, "base_url"):
        openai_module.base_url = proxy_url


# =============================================================================
# ANTHROPIC PATCHING
# =============================================================================


def _patch_anthropic(target, proxy_key: str, base_url: str) -> None:
    """
    Patch the Anthropic SDK to route through LLMLab proxy.

    The Anthropic client takes api_key and base_url in the constructor.
    We patch __init__ to override these and inject tag headers.
    """
    proxy_url = f"{base_url}/api/v1/proxy/anthropic"

    if hasattr(target, "Anthropic"):
        _original_init = target.Anthropic.__init__

        def _patched_init(self, *args, **kwargs):
            kwargs["base_url"] = proxy_url
            kwargs["api_key"] = proxy_key
            existing_headers = kwargs.get("default_headers", {}) or {}
            existing_headers.update(_build_tag_headers())
            if existing_headers:
                kwargs["default_headers"] = existing_headers
            _original_init(self, *args, **kwargs)

        target.Anthropic.__init__ = _patched_init

        # Also patch AsyncAnthropic if it exists
        if hasattr(target, "AsyncAnthropic"):
            _original_async_init = target.AsyncAnthropic.__init__

            def _patched_async_init(self, *args, **kwargs):
                kwargs["base_url"] = proxy_url
                kwargs["api_key"] = proxy_key
                existing_headers = kwargs.get("default_headers", {}) or {}
                existing_headers.update(_build_tag_headers())
                if existing_headers:
                    kwargs["default_headers"] = existing_headers
                _original_async_init(self, *args, **kwargs)

            target.AsyncAnthropic.__init__ = _patched_async_init


# =============================================================================
# GOOGLE PATCHING
# =============================================================================


def _patch_google(target, proxy_key: str, base_url: str) -> None:
    """
    Patch the Google Generative AI SDK to route through LLMLab proxy.

    Google's genai SDK uses genai.configure(api_key=...) and constructs
    URLs internally. We patch the configure function and the internal
    request mechanism to redirect to LLMLab proxy, and store tags.
    """
    proxy_url = f"{base_url}/api/v1/proxy/google"

    if hasattr(target, "configure"):
        _original_configure = target.configure

        def _patched_configure(*args, **kwargs):
            # Always use the proxy key
            kwargs["api_key"] = proxy_key
            # Store proxy URL for transport patching
            target._llmlab_proxy_url = proxy_url
            target._llmlab_tags = _current_tags
            _original_configure(*args, **kwargs)

        target.configure = _patched_configure

    # Patch GenerativeModel if available to intercept generate_content calls
    if hasattr(target, "GenerativeModel"):
        _original_model_init = target.GenerativeModel.__init__

        def _patched_model_init(self, *args, **kwargs):
            _original_model_init(self, *args, **kwargs)
            # Store proxy info on the model instance
            self._llmlab_proxy_url = proxy_url
            self._llmlab_proxy_key = proxy_key
            self._llmlab_tags = _current_tags

        target.GenerativeModel.__init__ = _patched_model_init


# =============================================================================
# UNPATCH (for testing)
# =============================================================================

_original_inits: dict = {}


def unpatch(target) -> None:
    """
    Remove LLMLab patching from a library.

    Useful for testing or when you want to temporarily bypass the proxy.

    Args:
        target: The previously patched library module.
    """
    module_name = _get_module_name(target)

    # Restore original __init__ methods if stored
    if module_name in _original_inits:
        for attr_path, original_fn in _original_inits[module_name].items():
            obj = target
            parts = attr_path.split(".")
            for part in parts[:-1]:
                obj = getattr(obj, part)
            setattr(obj, parts[-1], original_fn)
        del _original_inits[module_name]
