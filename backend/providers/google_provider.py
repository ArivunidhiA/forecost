"""
Google Gemini provider for cost calculation and API proxying.

Pricing updated: February 2026
Source: https://ai.google.dev/pricing
"""

from typing import Any, AsyncIterator, Dict, Optional, Tuple

import httpx

# Google Gemini pricing per 1M tokens (input, output)
# Updated February 2026
GOOGLE_PRICING: Dict[str, Dict[str, float]] = {
    # Gemini 2.0 Flash
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-001": {"input": 0.10, "output": 0.40},
    # Gemini 1.5 Pro
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-pro-002": {"input": 1.25, "output": 5.00},
    "gemini-1.5-pro-001": {"input": 1.25, "output": 5.00},
    # Gemini 1.5 Flash
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-flash-002": {"input": 0.075, "output": 0.30},
    "gemini-1.5-flash-001": {"input": 0.075, "output": 0.30},
    # Gemini 1.5 Flash-8B
    "gemini-1.5-flash-8b": {"input": 0.0375, "output": 0.15},
    "gemini-1.5-flash-8b-001": {"input": 0.0375, "output": 0.15},
    # Gemini 1.0 Pro
    "gemini-1.0-pro": {"input": 0.50, "output": 1.50},
    "gemini-pro": {"input": 0.50, "output": 1.50},
    # Embeddings
    "text-embedding-004": {"input": 0.00, "output": 0.00},
}

# Default pricing for unknown Google models
DEFAULT_GOOGLE_PRICING = {"input": 1.25, "output": 5.00}


class GoogleProvider:
    """
    Google Gemini provider for proxying requests and calculating costs.

    Handles:
    - GenerateContent (/v1beta/models/{model}:generateContent)
    - StreamGenerateContent (/v1beta/models/{model}:streamGenerateContent)
    """

    BASE_URL = "https://generativelanguage.googleapis.com"
    PROVIDER_NAME = "google"

    @staticmethod
    def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost for a Google Gemini API call.

        Args:
            model: Model name (e.g., "gemini-1.5-pro").
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            float: Cost in USD.
        """
        pricing = GOOGLE_PRICING.get(model, DEFAULT_GOOGLE_PRICING)

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return round(input_cost + output_cost, 6)

    @staticmethod
    def extract_usage(response_data: Dict[str, Any]) -> Tuple[int, int]:
        """
        Extract token usage from Google Gemini API response.

        Args:
            response_data: Parsed JSON response from Gemini.

        Returns:
            Tuple[int, int]: (input_tokens, output_tokens)
        """
        usage = response_data.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)
        return input_tokens, output_tokens

    @staticmethod
    def extract_model(response_data: Dict[str, Any], request_model: str) -> str:
        """
        Extract actual model used from response.

        Args:
            response_data: Parsed JSON response from Gemini.
            request_model: Model requested (fallback).

        Returns:
            str: Model name.
        """
        return response_data.get("modelVersion", request_model)

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
        Proxy a request to Google Gemini API.

        Args:
            api_key: User's real Google API key.
            path: API path.
            method: HTTP method.
            headers: Request headers.
            body: Request body.
            timeout: Request timeout in seconds.

        Returns:
            httpx.Response: Response from Google.
        """
        # Build URL with API key as query parameter (Google style)
        url = f"{GoogleProvider.BASE_URL}{path}"
        if "?" in url:
            url += f"&key={api_key}"
        else:
            url += f"?key={api_key}"

        # Prepare headers
        proxy_headers = {
            k: v for k, v in headers.items()
            if k.lower() not in ("host", "authorization", "x-api-key", "content-length")
        }

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
        Stream a request to Google Gemini API, yielding chunks.

        First yield: (status_code, response_headers) tuple.
        Subsequent yields: raw bytes chunks.
        """
        url = f"{GoogleProvider.BASE_URL}{path}"
        if "?" in url:
            url += f"&key={api_key}"
        else:
            url += f"?key={api_key}"

        proxy_headers = {
            k: v for k, v in headers.items()
            if k.lower() not in ("host", "authorization", "x-api-key", "content-length")
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(method, url, headers=proxy_headers, content=body) as response:
                yield response.status_code, dict(response.headers)
                async for chunk in response.aiter_bytes():
                    yield chunk
