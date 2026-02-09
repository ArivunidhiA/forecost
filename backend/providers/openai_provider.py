"""
OpenAI provider for cost calculation and API proxying.

Pricing updated: February 2026
Source: https://openai.com/pricing
"""

from typing import Any, AsyncIterator, Dict, Optional, Tuple

import httpx

# OpenAI pricing per 1M tokens (input, output)
# Updated February 2026
OPENAI_PRICING: Dict[str, Dict[str, float]] = {
    # GPT-4o (latest)
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-2024-11-20": {"input": 2.50, "output": 10.00},
    "gpt-4o-2024-08-06": {"input": 2.50, "output": 10.00},
    "gpt-4o-2024-05-13": {"input": 5.00, "output": 15.00},
    # GPT-4o mini
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o-mini-2024-07-18": {"input": 0.15, "output": 0.60},
    # GPT-4 Turbo
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4-turbo-2024-04-09": {"input": 10.00, "output": 30.00},
    "gpt-4-turbo-preview": {"input": 10.00, "output": 30.00},
    "gpt-4-1106-preview": {"input": 10.00, "output": 30.00},
    "gpt-4-0125-preview": {"input": 10.00, "output": 30.00},
    # GPT-4 (original)
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-4-0613": {"input": 30.00, "output": 60.00},
    "gpt-4-32k": {"input": 60.00, "output": 120.00},
    "gpt-4-32k-0613": {"input": 60.00, "output": 120.00},
    # GPT-3.5 Turbo
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gpt-3.5-turbo-0125": {"input": 0.50, "output": 1.50},
    "gpt-3.5-turbo-1106": {"input": 1.00, "output": 2.00},
    "gpt-3.5-turbo-instruct": {"input": 1.50, "output": 2.00},
    # o1 reasoning models
    "o1": {"input": 15.00, "output": 60.00},
    "o1-2024-12-17": {"input": 15.00, "output": 60.00},
    "o1-preview": {"input": 15.00, "output": 60.00},
    "o1-preview-2024-09-12": {"input": 15.00, "output": 60.00},
    "o1-mini": {"input": 3.00, "output": 12.00},
    "o1-mini-2024-09-12": {"input": 3.00, "output": 12.00},
    # o3 mini (latest reasoning)
    "o3-mini": {"input": 1.10, "output": 4.40},
    "o3-mini-2025-01-31": {"input": 1.10, "output": 4.40},
    # Embeddings
    "text-embedding-3-small": {"input": 0.02, "output": 0.00},
    "text-embedding-3-large": {"input": 0.13, "output": 0.00},
    "text-embedding-ada-002": {"input": 0.10, "output": 0.00},
}

# Default pricing for unknown models
DEFAULT_OPENAI_PRICING = {"input": 10.00, "output": 30.00}


class OpenAIProvider:
    """
    OpenAI provider for proxying requests and calculating costs.

    Handles:
    - Chat completions (/v1/chat/completions)
    - Completions (/v1/completions)
    - Embeddings (/v1/embeddings)
    """

    BASE_URL = "https://api.openai.com"
    PROVIDER_NAME = "openai"

    @staticmethod
    def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost for an OpenAI API call.

        Args:
            model: Model name (e.g., "gpt-4o", "gpt-3.5-turbo").
            input_tokens: Number of input/prompt tokens.
            output_tokens: Number of output/completion tokens.

        Returns:
            float: Cost in USD.

        Example:
            >>> OpenAIProvider.calculate_cost("gpt-4o", 1000, 500)
            0.0075  # $0.0025 input + $0.005 output
        """
        pricing = OPENAI_PRICING.get(model, DEFAULT_OPENAI_PRICING)

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return round(input_cost + output_cost, 6)

    @staticmethod
    def extract_usage(response_data: Dict[str, Any]) -> Tuple[int, int]:
        """
        Extract token usage from OpenAI API response.

        Args:
            response_data: Parsed JSON response from OpenAI.

        Returns:
            Tuple[int, int]: (input_tokens, output_tokens)
        """
        usage = response_data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        return input_tokens, output_tokens

    @staticmethod
    def extract_model(response_data: Dict[str, Any], request_model: str) -> str:
        """
        Extract actual model used from response.

        Args:
            response_data: Parsed JSON response from OpenAI.
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
        Proxy a request to OpenAI API.

        Args:
            api_key: User's real OpenAI API key.
            path: API path (e.g., "/v1/chat/completions").
            method: HTTP method.
            headers: Request headers (Authorization will be overwritten).
            body: Request body.
            timeout: Request timeout in seconds.

        Returns:
            httpx.Response: Response from OpenAI.
        """
        # Build URL
        url = f"{OpenAIProvider.BASE_URL}{path}"

        # Prepare headers (replace auth)
        proxy_headers = {k: v for k, v in headers.items() if k.lower() not in ("host", "authorization", "content-length")}
        proxy_headers["Authorization"] = f"Bearer {api_key}"

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
        Stream a request to OpenAI API, yielding chunks.

        First yield: (status_code, response_headers) tuple.
        Subsequent yields: raw bytes chunks.

        Args:
            api_key: User's real OpenAI API key.
            path: API path.
            method: HTTP method.
            headers: Request headers.
            body: Request body.
            timeout: Request timeout in seconds.
        """
        url = f"{OpenAIProvider.BASE_URL}{path}"
        proxy_headers = {k: v for k, v in headers.items() if k.lower() not in ("host", "authorization", "content-length")}
        proxy_headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(method, url, headers=proxy_headers, content=body) as response:
                yield response.status_code, dict(response.headers)
                async for chunk in response.aiter_bytes():
                    yield chunk
