"""
Anthropic provider for cost calculation and API proxying.

Pricing updated: February 2026
Source: https://www.anthropic.com/pricing
"""

from typing import Any, AsyncIterator, Dict, Optional, Tuple

import httpx

# Anthropic pricing per 1M tokens (input, output)
# Updated February 2026
ANTHROPIC_PRICING: Dict[str, Dict[str, float]] = {
    # Claude 3.5 Sonnet (latest)
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-latest": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20240620": {"input": 3.00, "output": 15.00},
    # Claude 3.5 Haiku
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-5-haiku-latest": {"input": 0.80, "output": 4.00},
    # Claude 3 Opus
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-opus-latest": {"input": 15.00, "output": 75.00},
    # Claude 3 Sonnet
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
    # Claude 3 Haiku
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    # Legacy Claude 2
    "claude-2.1": {"input": 8.00, "output": 24.00},
    "claude-2.0": {"input": 8.00, "output": 24.00},
    # Claude Instant
    "claude-instant-1.2": {"input": 0.80, "output": 2.40},
}

# Default pricing for unknown models
DEFAULT_ANTHROPIC_PRICING = {"input": 3.00, "output": 15.00}


class AnthropicProvider:
    """
    Anthropic provider for proxying requests and calculating costs.

    Handles:
    - Messages API (/v1/messages)
    - Completions API (/v1/complete) [legacy]
    """

    BASE_URL = "https://api.anthropic.com"
    PROVIDER_NAME = "anthropic"

    @staticmethod
    def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost for an Anthropic API call.

        Args:
            model: Model name (e.g., "claude-3-5-sonnet-20241022").
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            float: Cost in USD.

        Example:
            >>> AnthropicProvider.calculate_cost("claude-3-5-sonnet-20241022", 1000, 500)
            0.0105  # $0.003 input + $0.0075 output
        """
        pricing = ANTHROPIC_PRICING.get(model, DEFAULT_ANTHROPIC_PRICING)

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return round(input_cost + output_cost, 6)

    @staticmethod
    def extract_usage(response_data: Dict[str, Any]) -> Tuple[int, int]:
        """
        Extract token usage from Anthropic API response.

        Args:
            response_data: Parsed JSON response from Anthropic.

        Returns:
            Tuple[int, int]: (input_tokens, output_tokens)
        """
        usage = response_data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        return input_tokens, output_tokens

    @staticmethod
    def extract_model(response_data: Dict[str, Any], request_model: str) -> str:
        """
        Extract actual model used from response.

        Args:
            response_data: Parsed JSON response from Anthropic.
            request_model: Model requested (fallback).

        Returns:
            str: Model name.
        """
        return response_data.get("model", request_model)

    @staticmethod
    async def proxy_request(
        api_key: str,
        path: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[bytes] = None,
        timeout: float = 120.0,
    ) -> httpx.Response:
        """
        Proxy a request to Anthropic API.

        Args:
            api_key: User's real Anthropic API key.
            path: API path (e.g., "/v1/messages").
            method: HTTP method.
            headers: Request headers.
            body: Request body.
            timeout: Request timeout in seconds.

        Returns:
            httpx.Response: Response from Anthropic.
        """
        # Build URL
        url = f"{AnthropicProvider.BASE_URL}{path}"

        # Prepare headers
        proxy_headers = {
            k: v for k, v in headers.items()
            if k.lower() not in ("host", "x-api-key", "authorization", "content-length")
        }
        proxy_headers["x-api-key"] = api_key
        proxy_headers["anthropic-version"] = headers.get("anthropic-version", "2023-06-01")

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=proxy_headers,
                content=body,
            )
            return response

    @staticmethod
    async def stream_request(
        api_key: str,
        path: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[bytes] = None,
        timeout: float = 120.0,
    ) -> AsyncIterator:
        """
        Stream a request to Anthropic API, yielding chunks.

        First yield: (status_code, response_headers) tuple.
        Subsequent yields: raw bytes chunks.
        """
        url = f"{AnthropicProvider.BASE_URL}{path}"
        proxy_headers = {
            k: v for k, v in headers.items()
            if k.lower() not in ("host", "x-api-key", "authorization", "content-length")
        }
        proxy_headers["x-api-key"] = api_key
        proxy_headers["anthropic-version"] = headers.get("anthropic-version", "2023-06-01")

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(method, url, headers=proxy_headers, content=body) as response:
                yield response.status_code, dict(response.headers)
                async for chunk in response.aiter_bytes():
                    yield chunk
