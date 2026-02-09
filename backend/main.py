"""
LLMLab Backend API

A proxy-based LLM cost tracking service with caching, latency tracking,
budget alerts, tags, export, forecasting, and anomaly detection.

Endpoints:
- POST /auth/github: GitHub OAuth authentication
- GET /api/v1/me: Get current user
- POST /api/v1/keys: Store encrypted API key
- GET /api/v1/keys: Get proxy keys
- DELETE /api/v1/keys/{key_id}: Delete an API key
- POST /api/v1/proxy/openai: Proxy OpenAI requests (with caching + latency)
- POST /api/v1/proxy/anthropic: Proxy Anthropic requests (with caching + latency)
- POST /api/v1/proxy/google: Proxy Google Gemini requests (with caching + latency)
- GET /api/v1/stats: Get usage statistics (includes latency + cache stats + tag filter)
- GET /api/v1/stats/heatmap: Get usage heatmap (day x hour)
- GET /api/v1/stats/comparison: Get provider cost comparison
- GET /api/v1/stats/forecast: Get cost forecast
- GET /api/v1/stats/anomalies: Get anomaly events
- GET /api/v1/logs: List usage logs (paginated, filterable)
- GET /api/v1/logs/{log_id}: Get single log entry
- POST /api/v1/tags: Create a tag
- GET /api/v1/tags: List user's tags
- DELETE /api/v1/tags/{tag_id}: Delete a tag
- POST /api/v1/logs/{log_id}/tags: Attach tags to a log
- DELETE /api/v1/logs/{log_id}/tags/{tag_id}: Detach tag from a log
- GET /api/v1/export/csv: Export logs as CSV
- GET /api/v1/export/json: Export logs as JSON
- GET /api/v1/budgets: Get user budgets
- POST /api/v1/budgets: Create/update budget
- DELETE /api/v1/budgets/{budget_id}: Delete budget
- GET /api/v1/recommendations: Get cost optimization recommendations
- POST /api/v1/webhooks: Register a webhook
- GET /api/v1/webhooks: List user's webhooks
- DELETE /api/v1/webhooks/{webhook_id}: Delete a webhook
- GET /api/v1/cache/stats: Get cache statistics
- DELETE /api/v1/cache: Clear cache
- GET /health: Health check
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from auth import create_access_token, exchange_github_code, get_current_user
from config import get_settings
from database import get_db, init_db
from models import ApiKey, Budget, Tag, UsageLog, User, Webhook, usage_log_tags
from providers import AnthropicProvider, GoogleProvider, OpenAIProvider
from engines.recommendations_engine import RecommendationsEngine
from cache import response_cache
from alerts import check_and_fire_alerts
from anomaly import detect_anomalies, check_and_fire_anomaly_alerts
from schemas import (
    ApiKeyCreate,
    ApiKeyListResponse,
    ApiKeyResponse,
    AuthResponse,
    BudgetCreate,
    BudgetListResponse,
    BudgetResponse,
    CacheStatsResponse,
    ComparisonAlternative,
    ComparisonItem,
    ComparisonResponse,
    DailyCost,
    ErrorResponse,
    GitHubAuthRequest,
    HealthResponse,
    HeatmapCell,
    HeatmapResponse,
    ModelCost,
    RecommendationsResponse,
    StatsResponse,
    TagAttach,
    TagCreate,
    TagListResponse,
    TagResponse,
    UsageLogResponse,
    UsageLogsListResponse,
    UserResponse,
    WebhookCreate,
    WebhookListResponse,
    WebhookResponse,
    ForecastResponse,
    AnomalyEvent,
    AnomalyResponse,
)
from security import decrypt_api_key, encrypt_api_key

# =============================================================================
# APP INITIALIZATION
# =============================================================================

# Track server start time
SERVER_START_TIME = time.time()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="LLMLab API",
    description="Proxy-based LLM cost tracking service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add rate limit error handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"success": False, "error": "Rate limit exceeded. Try again later."},
    )


# CORS Middleware
@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    init_db()


# =============================================================================
# HEALTH CHECK
# =============================================================================


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    """
    Check API health and database connectivity.

    Returns service status, database connection, and uptime.
    """
    try:
        # Test database connection
        db.execute("SELECT 1")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    uptime = int(time.time() - SERVER_START_TIME)

    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        database=db_status,
        version="1.0.0",
        uptime_seconds=uptime,
    )


# =============================================================================
# AUTHENTICATION
# =============================================================================


@app.post("/auth/github", response_model=AuthResponse, tags=["Authentication"])
async def github_auth(
    request: GitHubAuthRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """
    Authenticate via GitHub OAuth.

    Exchange a GitHub OAuth code for a JWT token.
    Creates a new user if first login.

    Args:
        request: Contains GitHub OAuth authorization code.

    Returns:
        AuthResponse: User info and JWT token.
    """
    # Exchange code for GitHub user info
    github_user = await exchange_github_code(request.code)

    # Find or create user
    user = db.query(User).filter(User.github_id == github_user["id"]).first()

    if user is None:
        # Create new user
        user = User(
            github_id=github_user["id"],
            email=github_user["email"],
            username=github_user["username"],
            avatar_url=github_user["avatar_url"],
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update existing user info
        user.email = github_user["email"]
        user.username = github_user["username"]
        user.avatar_url = github_user["avatar_url"]
        db.commit()

    # Generate JWT token
    token, expires_in = create_access_token(user.id)

    return AuthResponse(
        user_id=user.id,
        email=user.email,
        username=user.username,
        token=token,
        expires_in=expires_in,
    )


@app.get("/api/v1/me", response_model=UserResponse, tags=["Authentication"])
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """
    Get current user's profile.

    Requires authentication.
    """
    return current_user


# =============================================================================
# API KEY MANAGEMENT
# =============================================================================


@app.post("/api/v1/keys", response_model=ApiKeyResponse, tags=["API Keys"])
@limiter.limit("10/minute")
async def create_api_key(
    request: Request,
    key_data: ApiKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiKeyResponse:
    """
    Store an encrypted API key for a provider.

    Your real API key is encrypted and stored securely.
    You receive a proxy key to use in your applications.

    Args:
        key_data: Provider name and your real API key.

    Returns:
        ApiKeyResponse: Proxy key and metadata.
    """
    # Check if user already has a key for this provider
    existing = db.query(ApiKey).filter(
        ApiKey.user_id == current_user.id,
        ApiKey.provider == key_data.provider,
        ApiKey.is_active == True,
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You already have an active key for {key_data.provider}. Delete it first to add a new one.",
        )

    # Encrypt the API key
    encrypted = encrypt_api_key(key_data.api_key)

    # Create API key record
    api_key = ApiKey(
        user_id=current_user.id,
        provider=key_data.provider,
        encrypted_key=encrypted,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return ApiKeyResponse(
        id=api_key.id,
        provider=api_key.provider,
        proxy_key=api_key.proxy_key,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        is_active=api_key.is_active,
    )


@app.get("/api/v1/keys", response_model=ApiKeyListResponse, tags=["API Keys"])
async def list_api_keys(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiKeyListResponse:
    """
    List all your API keys (proxy keys).

    Returns proxy keys for each provider you've configured.
    Your real API keys are never returned.
    """
    keys = db.query(ApiKey).filter(
        ApiKey.user_id == current_user.id,
        ApiKey.is_active == True,
    ).all()

    return ApiKeyListResponse(
        keys=[
            ApiKeyResponse(
                id=k.id,
                provider=k.provider,
                proxy_key=k.proxy_key,
                created_at=k.created_at,
                last_used_at=k.last_used_at,
                is_active=k.is_active,
            )
            for k in keys
        ]
    )


@app.delete("/api/v1/keys/{key_id}", tags=["API Keys"])
async def delete_api_key(
    key_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete an API key.

    Deactivates the key so it can no longer be used.
    """
    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id,
        ApiKey.user_id == current_user.id,
    ).first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    api_key.is_active = False
    db.commit()

    return {"success": True, "message": "API key deleted"}


# =============================================================================
# PROXY ENDPOINTS
# =============================================================================


async def get_api_key_by_proxy(proxy_key: str, provider: str, db: Session) -> ApiKey:
    """
    Lookup API key by proxy key and provider.

    Args:
        proxy_key: The proxy key from request header.
        provider: Expected provider (openai, anthropic).
        db: Database session.

    Returns:
        ApiKey: The API key record.

    Raises:
        HTTPException: If key not found or invalid.
    """
    api_key = db.query(ApiKey).filter(
        ApiKey.proxy_key == proxy_key,
        ApiKey.provider == provider,
        ApiKey.is_active == True,
    ).first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or missing proxy key for {provider}",
        )

    return api_key


def extract_proxy_key(request: Request) -> str:
    """
    Extract proxy key from request headers.

    Supports:
    - Authorization: Bearer llmlab_pk_xxx
    - x-api-key: llmlab_pk_xxx
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()

    api_key = request.headers.get("x-api-key", "")
    if api_key:
        return api_key.strip()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing proxy key. Include 'Authorization: Bearer <proxy_key>' header.",
    )


def _auto_tag_log(request: Request, usage_log: UsageLog, db: Session):
    """
    Auto-attach tags from X-LLMLab-Tags header to a usage log.
    Creates tags on-the-fly if they don't exist yet.
    """
    tag_header = request.headers.get("x-llmlab-tags", "")
    if not tag_header:
        return

    tag_names = [t.strip() for t in tag_header.split(",") if t.strip()]
    user_id = usage_log.user_id

    for name in tag_names:
        tag = db.query(Tag).filter(Tag.user_id == user_id, Tag.name == name).first()
        if not tag:
            tag = Tag(user_id=user_id, name=name)
            db.add(tag)
            db.flush()
        if tag not in usage_log.tags:
            usage_log.tags.append(tag)

    db.commit()


async def _stream_and_log(
    provider_name: str,
    provider_cls,
    real_api_key: str,
    provider_path: str,
    method: str,
    headers: dict,
    body: bytes,
    request_model: str,
    api_key_record,
    db: Session,
    request: Request = None,
):
    """
    Async generator that streams provider response chunks to the client
    while accumulating SSE data for usage logging after stream ends.
    """
    accumulated = bytearray()
    start_time = time.monotonic()
    input_tokens, output_tokens = 0, 0
    actual_model = request_model

    stream = provider_cls.stream_request(
        api_key=real_api_key,
        path=provider_path,
        method=method,
        headers=headers,
        body=body,
    )

    first = True
    async for chunk in stream:
        if first:
            # First yield is (status_code, headers) — skip, we set these on StreamingResponse
            first = False
            continue
        accumulated.extend(chunk)
        yield chunk

    latency_ms = round((time.monotonic() - start_time) * 1000, 2)

    # Try to parse accumulated SSE data for usage info
    try:
        text = accumulated.decode("utf-8", errors="replace")
        # OpenAI and Anthropic SSE format: look for usage in final events
        for line in reversed(text.split("\n")):
            line = line.strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    event_data = json.loads(line[6:])
                    # OpenAI: usage in final chunk
                    if "usage" in event_data:
                        usage = event_data["usage"]
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)
                        actual_model = event_data.get("model", request_model)
                        break
                    # Anthropic: message_delta with usage
                    if event_data.get("type") == "message_delta" and "usage" in event_data:
                        output_tokens = event_data["usage"].get("output_tokens", 0)
                        break
                    if event_data.get("type") == "message_start" and "message" in event_data:
                        msg = event_data["message"]
                        if "usage" in msg:
                            input_tokens = msg["usage"].get("input_tokens", 0)
                        actual_model = msg.get("model", request_model)
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception:
        pass

    # Calculate cost and log
    cost = provider_cls.calculate_cost(actual_model, input_tokens, output_tokens)

    if input_tokens > 0 or output_tokens > 0:
        usage_log = UsageLog(
            user_id=api_key_record.user_id,
            provider=provider_name,
            model=actual_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        db.add(usage_log)
        api_key_record.last_used_at = datetime.utcnow()
        db.commit()

        # Auto-tag if request available
        if request is not None:
            _auto_tag_log(request, usage_log, db)

        asyncio.create_task(check_and_fire_alerts(api_key_record.user_id, db))
        asyncio.create_task(check_and_fire_anomaly_alerts(api_key_record.user_id, db))


@app.api_route(
    "/api/v1/proxy/openai/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    tags=["Proxy"],
)
@limiter.limit("100/minute")
async def proxy_openai(
    request: Request,
    path: str,
    db: Session = Depends(get_db),
):
    """
    Proxy requests to OpenAI API.

    Intercepts the request, forwards to OpenAI with your real API key,
    logs token usage and cost, then returns the response unchanged.

    Usage:
    - Set your base URL to: https://llmlab-api.example.com/api/v1/proxy/openai
    - Use your LLMLab proxy key as the API key
    - All requests will be proxied and tracked

    Example:
        ```python
        import openai
        openai.api_base = "https://llmlab-api.example.com/api/v1/proxy/openai"
        openai.api_key = "llmlab_pk_your_proxy_key"
        ```
    """
    # Extract proxy key
    proxy_key = extract_proxy_key(request)

    # Get API key record
    api_key_record = await get_api_key_by_proxy(proxy_key, "openai", db)

    # Decrypt real API key
    real_api_key = decrypt_api_key(api_key_record.encrypted_key)

    # Get request body
    body = await request.body()

    # Parse body to extract model (for cost calculation)
    request_model = "gpt-4o"  # Default
    is_streaming = False
    try:
        body_json = json.loads(body) if body else {}
        request_model = body_json.get("model", request_model)
        is_streaming = body_json.get("stream", False)
    except json.JSONDecodeError:
        pass

    # Streaming requests bypass cache and return SSE
    if is_streaming:
        openai_path = f"/v1/{path}"
        return StreamingResponse(
            _stream_and_log(
                provider_name="openai",
                provider_cls=OpenAIProvider,
                real_api_key=real_api_key,
                provider_path=openai_path,
                method=request.method,
                headers=dict(request.headers),
                body=body,
                request_model=request_model,
                api_key_record=api_key_record,
                db=db,
                request=request,
            ),
            media_type="text/event-stream",
        )

    # Check cache first (non-streaming only)
    cached = response_cache.get(provider="openai", body=body)
    if cached:
        cached_body, cached_meta = cached
        usage_log = UsageLog(
            user_id=api_key_record.user_id,
            provider="openai",
            model=cached_meta.get("model", request_model),
            input_tokens=cached_meta.get("input_tokens", 0),
            output_tokens=cached_meta.get("output_tokens", 0),
            cost_usd=0.0,
            latency_ms=0.0,
            cache_hit=True,
        )
        db.add(usage_log)
        api_key_record.last_used_at = datetime.utcnow()
        db.commit()
        _auto_tag_log(request, usage_log, db)
        return Response(
            content=cached_body,
            status_code=cached_meta.get("status_code", 200),
            media_type=cached_meta.get("content_type", "application/json"),
        )

    # Proxy to OpenAI with latency measurement
    openai_path = f"/v1/{path}"
    headers = dict(request.headers)

    start_time = time.monotonic()
    response = await OpenAIProvider.proxy_request(
        api_key=real_api_key,
        path=openai_path,
        method=request.method,
        headers=headers,
        body=body,
    )
    latency_ms = round((time.monotonic() - start_time) * 1000, 2)

    # Parse response for usage tracking
    response_body = response.content
    input_tokens, output_tokens = 0, 0
    actual_model = request_model

    if response.status_code == 200:
        try:
            response_json = response.json()
            input_tokens, output_tokens = OpenAIProvider.extract_usage(response_json)
            actual_model = OpenAIProvider.extract_model(response_json, request_model)
        except Exception:
            pass

    # Calculate cost
    cost = OpenAIProvider.calculate_cost(actual_model, input_tokens, output_tokens)

    # Store in cache on success
    if response.status_code == 200 and (input_tokens > 0 or output_tokens > 0):
        response_cache.set(
            provider="openai",
            body=body,
            response_body=response_body,
            metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model": actual_model,
                "cost_usd": cost,
                "content_type": response.headers.get("content-type", "application/json"),
                "status_code": response.status_code,
            },
        )

    # Log usage
    if input_tokens > 0 or output_tokens > 0:
        usage_log = UsageLog(
            user_id=api_key_record.user_id,
            provider="openai",
            model=actual_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        db.add(usage_log)

        # Update last used timestamp
        api_key_record.last_used_at = datetime.utcnow()
        db.commit()

        # Check budget alerts and anomaly (fire-and-forget)
        asyncio.create_task(check_and_fire_alerts(api_key_record.user_id, db))
        asyncio.create_task(check_and_fire_anomaly_alerts(api_key_record.user_id, db))
        _auto_tag_log(request, usage_log, db)

    # Return response with original headers
    return Response(
        content=response_body,
        status_code=response.status_code,
        headers={
            k: v for k, v in response.headers.items()
            if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")
        },
        media_type=response.headers.get("content-type"),
    )


@app.api_route(
    "/api/v1/proxy/anthropic/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    tags=["Proxy"],
)
@limiter.limit("100/minute")
async def proxy_anthropic(
    request: Request,
    path: str,
    db: Session = Depends(get_db),
):
    """
    Proxy requests to Anthropic API.

    Intercepts the request, forwards to Anthropic with your real API key,
    logs token usage and cost, then returns the response unchanged.

    Usage:
    - Set your base URL to: https://llmlab-api.example.com/api/v1/proxy/anthropic
    - Use your LLMLab proxy key in x-api-key header
    - All requests will be proxied and tracked

    Example:
        ```python
        import anthropic
        client = anthropic.Anthropic(
            base_url="https://llmlab-api.example.com/api/v1/proxy/anthropic",
            api_key="llmlab_pk_your_proxy_key"
        )
        ```
    """
    # Extract proxy key
    proxy_key = extract_proxy_key(request)

    # Get API key record
    api_key_record = await get_api_key_by_proxy(proxy_key, "anthropic", db)

    # Decrypt real API key
    real_api_key = decrypt_api_key(api_key_record.encrypted_key)

    # Get request body
    body = await request.body()

    # Parse body to extract model
    request_model = "claude-3-5-sonnet-20241022"  # Default
    is_streaming = False
    try:
        body_json = json.loads(body) if body else {}
        request_model = body_json.get("model", request_model)
        is_streaming = body_json.get("stream", False)
    except json.JSONDecodeError:
        pass

    # Streaming requests bypass cache and return SSE
    if is_streaming:
        anthropic_path = f"/v1/{path}"
        return StreamingResponse(
            _stream_and_log(
                provider_name="anthropic",
                provider_cls=AnthropicProvider,
                real_api_key=real_api_key,
                provider_path=anthropic_path,
                method=request.method,
                headers=dict(request.headers),
                body=body,
                request_model=request_model,
                api_key_record=api_key_record,
                db=db,
                request=request,
            ),
            media_type="text/event-stream",
        )

    # Check cache first (non-streaming only)
    cached = response_cache.get(provider="anthropic", body=body)
    if cached:
        cached_body, cached_meta = cached
        usage_log = UsageLog(
            user_id=api_key_record.user_id,
            provider="anthropic",
            model=cached_meta.get("model", request_model),
            input_tokens=cached_meta.get("input_tokens", 0),
            output_tokens=cached_meta.get("output_tokens", 0),
            cost_usd=0.0,
            latency_ms=0.0,
            cache_hit=True,
        )
        db.add(usage_log)
        api_key_record.last_used_at = datetime.utcnow()
        db.commit()
        _auto_tag_log(request, usage_log, db)
        return Response(
            content=cached_body,
            status_code=cached_meta.get("status_code", 200),
            media_type=cached_meta.get("content_type", "application/json"),
        )

    # Proxy to Anthropic with latency measurement
    anthropic_path = f"/v1/{path}"
    headers = dict(request.headers)

    start_time = time.monotonic()
    response = await AnthropicProvider.proxy_request(
        api_key=real_api_key,
        path=anthropic_path,
        method=request.method,
        headers=headers,
        body=body,
    )
    latency_ms = round((time.monotonic() - start_time) * 1000, 2)

    # Parse response for usage tracking
    response_body = response.content
    input_tokens, output_tokens = 0, 0
    actual_model = request_model

    if response.status_code == 200:
        try:
            response_json = response.json()
            input_tokens, output_tokens = AnthropicProvider.extract_usage(response_json)
            actual_model = AnthropicProvider.extract_model(response_json, request_model)
        except Exception:
            pass

    # Calculate cost
    cost = AnthropicProvider.calculate_cost(actual_model, input_tokens, output_tokens)

    # Store in cache on success
    if response.status_code == 200 and (input_tokens > 0 or output_tokens > 0):
        response_cache.set(
            provider="anthropic",
            body=body,
            response_body=response_body,
            metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model": actual_model,
                "cost_usd": cost,
                "content_type": response.headers.get("content-type", "application/json"),
                "status_code": response.status_code,
            },
        )

    # Log usage
    if input_tokens > 0 or output_tokens > 0:
        usage_log = UsageLog(
            user_id=api_key_record.user_id,
            provider="anthropic",
            model=actual_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        db.add(usage_log)

        # Update last used timestamp
        api_key_record.last_used_at = datetime.utcnow()
        db.commit()

        # Check budget alerts and anomaly (fire-and-forget)
        asyncio.create_task(check_and_fire_alerts(api_key_record.user_id, db))
        asyncio.create_task(check_and_fire_anomaly_alerts(api_key_record.user_id, db))
        _auto_tag_log(request, usage_log, db)

    # Return response with original headers
    return Response(
        content=response_body,
        status_code=response.status_code,
        headers={
            k: v for k, v in response.headers.items()
            if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")
        },
        media_type=response.headers.get("content-type"),
    )


@app.api_route(
    "/api/v1/proxy/google/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    tags=["Proxy"],
)
@limiter.limit("100/minute")
async def proxy_google(
    request: Request,
    path: str,
    db: Session = Depends(get_db),
):
    """
    Proxy requests to Google Gemini API.

    Intercepts the request, forwards to Google with your real API key,
    logs token usage and cost, then returns the response unchanged.
    """
    proxy_key = extract_proxy_key(request)
    api_key_record = await get_api_key_by_proxy(proxy_key, "google", db)
    real_api_key = decrypt_api_key(api_key_record.encrypted_key)

    body = await request.body()

    request_model = "gemini-1.5-flash"
    is_streaming = False
    try:
        body_json = json.loads(body) if body else {}
        request_model = body_json.get("model", request_model)
        is_streaming = body_json.get("stream", False)
    except json.JSONDecodeError:
        pass

    # Streaming requests bypass cache and return SSE
    if is_streaming:
        google_path = f"/{path}"
        return StreamingResponse(
            _stream_and_log(
                provider_name="google",
                provider_cls=GoogleProvider,
                real_api_key=real_api_key,
                provider_path=google_path,
                method=request.method,
                headers=dict(request.headers),
                body=body,
                request_model=request_model,
                api_key_record=api_key_record,
                db=db,
                request=request,
            ),
            media_type="text/event-stream",
        )

    # Check cache first (non-streaming only)
    cached = response_cache.get(provider="google", body=body)
    if cached:
        cached_body, cached_meta = cached
        usage_log = UsageLog(
            user_id=api_key_record.user_id,
            provider="google",
            model=cached_meta.get("model", request_model),
            input_tokens=cached_meta.get("input_tokens", 0),
            output_tokens=cached_meta.get("output_tokens", 0),
            cost_usd=0.0,
            latency_ms=0.0,
            cache_hit=True,
        )
        db.add(usage_log)
        api_key_record.last_used_at = datetime.utcnow()
        db.commit()
        _auto_tag_log(request, usage_log, db)
        return Response(
            content=cached_body,
            status_code=cached_meta.get("status_code", 200),
            media_type=cached_meta.get("content_type", "application/json"),
        )

    # Proxy to Google with latency measurement
    google_path = f"/{path}"
    headers = dict(request.headers)

    start_time = time.monotonic()
    response = await GoogleProvider.proxy_request(
        api_key=real_api_key,
        path=google_path,
        method=request.method,
        headers=headers,
        body=body,
    )
    latency_ms = round((time.monotonic() - start_time) * 1000, 2)

    response_body = response.content
    input_tokens, output_tokens = 0, 0
    actual_model = request_model

    if response.status_code == 200:
        try:
            response_json = response.json()
            input_tokens, output_tokens = GoogleProvider.extract_usage(response_json)
            actual_model = GoogleProvider.extract_model(response_json, request_model)
        except Exception:
            pass

    cost = GoogleProvider.calculate_cost(actual_model, input_tokens, output_tokens)

    # Store in cache on success
    if response.status_code == 200 and (input_tokens > 0 or output_tokens > 0):
        response_cache.set(
            provider="google",
            body=body,
            response_body=response_body,
            metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model": actual_model,
                "cost_usd": cost,
                "content_type": response.headers.get("content-type", "application/json"),
                "status_code": response.status_code,
            },
        )

    if input_tokens > 0 or output_tokens > 0:
        usage_log = UsageLog(
            user_id=api_key_record.user_id,
            provider="google",
            model=actual_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        db.add(usage_log)
        api_key_record.last_used_at = datetime.utcnow()
        db.commit()

        # Check budget alerts and anomaly (fire-and-forget)
        asyncio.create_task(check_and_fire_alerts(api_key_record.user_id, db))
        asyncio.create_task(check_and_fire_anomaly_alerts(api_key_record.user_id, db))
        _auto_tag_log(request, usage_log, db)

    return Response(
        content=response_body,
        status_code=response.status_code,
        headers={
            k: v for k, v in response.headers.items()
            if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")
        },
        media_type=response.headers.get("content-type"),
    )


# =============================================================================
# STATS ENDPOINT
# =============================================================================


@app.get("/api/v1/stats", response_model=StatsResponse, tags=["Stats"])
async def get_stats(
    period: str = Query(
        default="month",
        description="Time period: today, week, month, or all",
        pattern="^(today|week|month|all)$",
    ),
    tag: Optional[str] = Query(None, description="Filter by tag name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StatsResponse:
    """
    Get usage statistics and costs.

    Args:
        period: Time period to query (today, week, month, all).

    Returns:
        StatsResponse: Total costs, breakdown by model and by day.
    """
    now = datetime.utcnow()

    # Calculate date range
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    else:  # all
        start_date = datetime(2000, 1, 1)  # Effectively all time

    # Base filter for the period
    base_filter = [
        UsageLog.user_id == current_user.id,
        UsageLog.created_at >= start_date,
    ]

    # Build a base query (just filters, no loading)
    base_query = db.query(UsageLog).filter(*base_filter)

    # Apply tag filter if specified
    if tag:
        base_query = base_query.join(UsageLog.tags).filter(Tag.name == tag)
        base_filter_with_tag = True
    else:
        base_filter_with_tag = False

    # --- Aggregate totals via SQL ---
    totals = base_query.with_entities(
        func.coalesce(func.sum(UsageLog.cost_usd), 0.0).label("total_usd"),
        func.count(UsageLog.id).label("total_calls"),
        func.coalesce(func.sum(UsageLog.input_tokens + UsageLog.output_tokens), 0).label("total_tokens"),
        func.avg(UsageLog.latency_ms).label("avg_latency_ms"),
        func.sum(case((UsageLog.cache_hit == True, 1), else_=0)).label("cache_hits"),
    ).first()

    total_usd = float(totals.total_usd or 0)
    total_calls = int(totals.total_calls or 0)
    total_tokens = int(totals.total_tokens or 0)
    avg_latency_ms = round(float(totals.avg_latency_ms), 2) if totals.avg_latency_ms else 0.0
    cache_hits = int(totals.cache_hits or 0)
    cache_misses = total_calls - cache_hits

    # --- Cache savings (requires provider pricing, query only cache-hit logs) ---
    cache_savings_usd = 0.0
    if cache_hits > 0:
        cache_hit_logs = base_query.filter(UsageLog.cache_hit == True).with_entities(
            UsageLog.provider, UsageLog.model, UsageLog.input_tokens, UsageLog.output_tokens
        ).all()
        provider_map = {"openai": OpenAIProvider, "anthropic": AnthropicProvider, "google": GoogleProvider}
        for log_row in cache_hit_logs:
            provider_cls = provider_map.get(log_row.provider)
            if provider_cls:
                cache_savings_usd += provider_cls.calculate_cost(log_row.model, log_row.input_tokens, log_row.output_tokens)

    # --- Group by model via SQL ---
    model_rows = base_query.with_entities(
        UsageLog.model,
        UsageLog.provider,
        func.sum(UsageLog.input_tokens + UsageLog.output_tokens).label("total_tokens"),
        func.sum(UsageLog.cost_usd).label("cost_usd"),
        func.count(UsageLog.id).label("call_count"),
        func.avg(UsageLog.latency_ms).label("avg_latency_ms"),
    ).group_by(UsageLog.model, UsageLog.provider).order_by(func.sum(UsageLog.cost_usd).desc()).all()

    by_model = [
        ModelCost(
            model=row.model,
            provider=row.provider,
            total_tokens=int(row.total_tokens or 0),
            cost_usd=round(float(row.cost_usd or 0), 6),
            call_count=int(row.call_count or 0),
            avg_latency_ms=round(float(row.avg_latency_ms), 2) if row.avg_latency_ms else None,
        )
        for row in model_rows
    ]

    # --- Group by day via SQL ---
    day_rows = base_query.with_entities(
        func.date(UsageLog.created_at).label("date"),
        func.sum(UsageLog.cost_usd).label("cost_usd"),
        func.count(UsageLog.id).label("call_count"),
    ).group_by(func.date(UsageLog.created_at)).order_by(func.date(UsageLog.created_at)).all()

    by_day = [
        DailyCost(
            date=str(row.date),
            cost_usd=round(float(row.cost_usd or 0), 6),
            call_count=int(row.call_count or 0),
        )
        for row in day_rows
    ]

    # --- Today / month / all-time summaries via SQL ---
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now - timedelta(days=30)

    summary = db.query(
        func.coalesce(func.sum(
            case((UsageLog.created_at >= today_start, UsageLog.cost_usd), else_=0.0)
        ), 0.0).label("today_usd"),
        func.coalesce(func.sum(
            case((UsageLog.created_at >= month_start, UsageLog.cost_usd), else_=0.0)
        ), 0.0).label("month_usd"),
        func.coalesce(func.sum(UsageLog.cost_usd), 0.0).label("all_time_usd"),
    ).filter(UsageLog.user_id == current_user.id).first()

    return StatsResponse(
        period=period,
        total_usd=round(total_usd, 6),
        total_calls=total_calls,
        total_tokens=total_tokens,
        avg_latency_ms=avg_latency_ms,
        today_usd=round(float(summary.today_usd or 0), 6),
        month_usd=round(float(summary.month_usd or 0), 6),
        all_time_usd=round(float(summary.all_time_usd or 0), 6),
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        cache_savings_usd=round(cache_savings_usd, 6),
        by_model=by_model,
        by_day=by_day,
    )


# =============================================================================
# BUDGET ENDPOINTS
# =============================================================================


@app.get("/api/v1/budgets", response_model=BudgetListResponse, tags=["Budgets"])
async def get_budgets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BudgetListResponse:
    """Get user's budgets with current spend status."""
    budgets = db.query(Budget).filter(Budget.user_id == current_user.id).all()

    now = datetime.utcnow()
    month_start = now - timedelta(days=30)

    current_spend = sum(
        log.cost_usd for log in db.query(UsageLog).filter(
            UsageLog.user_id == current_user.id,
            UsageLog.created_at >= month_start,
        ).all()
    )

    budget_responses = []
    for b in budgets:
        pct = (current_spend / b.amount_usd * 100) if b.amount_usd > 0 else 0
        if pct >= 100:
            budget_status = "exceeded"
        elif pct >= b.alert_threshold:
            budget_status = "warning"
        else:
            budget_status = "ok"

        budget_responses.append(BudgetResponse(
            id=b.id,
            amount_usd=b.amount_usd,
            period=b.period,
            alert_threshold=b.alert_threshold,
            current_spend=round(current_spend, 6),
            status=budget_status,
            created_at=b.created_at,
            updated_at=b.updated_at,
        ))

    return BudgetListResponse(budgets=budget_responses)


@app.post("/api/v1/budgets", response_model=BudgetResponse, tags=["Budgets"])
async def create_budget(
    budget_data: BudgetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BudgetResponse:
    """Create or update a monthly budget."""
    existing = db.query(Budget).filter(Budget.user_id == current_user.id).first()

    if existing:
        existing.amount_usd = budget_data.amount_usd
        existing.period = budget_data.period
        existing.alert_threshold = budget_data.alert_threshold
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        budget = existing
    else:
        budget = Budget(
            user_id=current_user.id,
            amount_usd=budget_data.amount_usd,
            period=budget_data.period,
            alert_threshold=budget_data.alert_threshold,
        )
        db.add(budget)
        db.commit()
        db.refresh(budget)

    now = datetime.utcnow()
    month_start = now - timedelta(days=30)
    current_spend = sum(
        log.cost_usd for log in db.query(UsageLog).filter(
            UsageLog.user_id == current_user.id,
            UsageLog.created_at >= month_start,
        ).all()
    )

    pct = (current_spend / budget.amount_usd * 100) if budget.amount_usd > 0 else 0
    if pct >= 100:
        budget_status = "exceeded"
    elif pct >= budget.alert_threshold:
        budget_status = "warning"
    else:
        budget_status = "ok"

    return BudgetResponse(
        id=budget.id,
        amount_usd=budget.amount_usd,
        period=budget.period,
        alert_threshold=budget.alert_threshold,
        current_spend=round(current_spend, 6),
        status=budget_status,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


@app.delete("/api/v1/budgets/{budget_id}", tags=["Budgets"])
async def delete_budget(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a budget."""
    budget = db.query(Budget).filter(
        Budget.id == budget_id,
        Budget.user_id == current_user.id,
    ).first()

    if not budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found",
        )

    db.delete(budget)
    db.commit()

    return {"success": True, "message": "Budget deleted"}


# =============================================================================
# RECOMMENDATIONS ENDPOINT
# =============================================================================


@app.get("/api/v1/recommendations", response_model=RecommendationsResponse, tags=["Recommendations"])
async def get_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RecommendationsResponse:
    """
    Get cost optimization recommendations based on usage patterns.

    Analyzes the last 30 days of usage and suggests model switches,
    caching strategies, and other optimizations.
    """
    now = datetime.utcnow()
    month_start = now - timedelta(days=30)

    logs = db.query(UsageLog).filter(
        UsageLog.user_id == current_user.id,
        UsageLog.created_at >= month_start,
    ).all()

    events = [
        {
            "model": log.model,
            "provider": log.provider,
            "cost": log.cost_usd,
            "input_tokens": log.input_tokens,
            "output_tokens": log.output_tokens,
            "timestamp": log.created_at,
        }
        for log in logs
    ]

    engine = RecommendationsEngine()
    result = engine.generate_recommendations(events)

    return RecommendationsResponse(**result)


# =============================================================================
# HEATMAP ENDPOINT
# =============================================================================


@app.get("/api/v1/stats/heatmap", response_model=HeatmapResponse, tags=["Stats"])
async def get_heatmap(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HeatmapResponse:
    """
    Get usage heatmap: calls aggregated by day-of-week and hour-of-day.

    Returns a grid of cells for visualization.
    """
    now = datetime.utcnow()
    month_start = now - timedelta(days=30)

    logs = db.query(UsageLog).filter(
        UsageLog.user_id == current_user.id,
        UsageLog.created_at >= month_start,
    ).all()

    # Aggregate by (day_of_week, hour)
    grid: dict[tuple[int, int], dict] = {}
    for log in logs:
        day = log.created_at.weekday()  # 0=Monday, 6=Sunday
        hour = log.created_at.hour
        key = (day, hour)
        if key not in grid:
            grid[key] = {"call_count": 0, "cost_usd": 0.0}
        grid[key]["call_count"] += 1
        grid[key]["cost_usd"] += log.cost_usd

    cells = [
        HeatmapCell(
            day=day,
            hour=hour,
            call_count=data["call_count"],
            cost_usd=round(data["cost_usd"], 6),
        )
        for (day, hour), data in sorted(grid.items())
    ]

    return HeatmapResponse(cells=cells)


# =============================================================================
# PROVIDER COMPARISON ENDPOINT
# =============================================================================


@app.get("/api/v1/stats/comparison", response_model=ComparisonResponse, tags=["Stats"])
async def get_comparison(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ComparisonResponse:
    """
    Compare actual costs against alternative providers.

    For each model the user has used, calculate what the equivalent cost
    would be on other providers using their pricing tables.
    """
    from providers import OPENAI_PRICING, ANTHROPIC_PRICING, GOOGLE_PRICING

    now = datetime.utcnow()
    month_start = now - timedelta(days=30)

    logs = db.query(UsageLog).filter(
        UsageLog.user_id == current_user.id,
        UsageLog.created_at >= month_start,
    ).all()

    # Aggregate by (model, provider)
    model_usage: dict[tuple[str, str], dict] = {}
    for log in logs:
        key = (log.model, log.provider)
        if key not in model_usage:
            model_usage[key] = {
                "actual_cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
        model_usage[key]["actual_cost"] += log.cost_usd
        model_usage[key]["input_tokens"] += log.input_tokens
        model_usage[key]["output_tokens"] += log.output_tokens

    # Build comparison capability mapping
    all_pricing = {
        "openai": OPENAI_PRICING,
        "anthropic": ANTHROPIC_PRICING,
        "google": GOOGLE_PRICING,
    }

    comparisons = []
    current_total = 0.0
    cheapest_total = 0.0

    for (model, provider), usage in model_usage.items():
        actual_cost = usage["actual_cost"]
        input_tokens = usage["input_tokens"]
        output_tokens = usage["output_tokens"]
        current_total += actual_cost

        alternatives = []
        cheapest_cost = actual_cost

        # Check all providers for alternative models
        for alt_provider, pricing in all_pricing.items():
            for alt_model, prices in pricing.items():
                # Skip the same model on the same provider
                if alt_provider == provider and alt_model == model:
                    continue
                est_cost = (
                    input_tokens * prices["input"] / 1_000_000
                    + output_tokens * prices["output"] / 1_000_000
                )
                alternatives.append(ComparisonAlternative(
                    provider=alt_provider,
                    model=alt_model,
                    estimated_cost=round(est_cost, 6),
                ))
                if est_cost < cheapest_cost:
                    cheapest_cost = est_cost

        # Sort alternatives by cost
        alternatives.sort(key=lambda a: a.estimated_cost)
        # Keep top 5 cheapest
        alternatives = alternatives[:5]

        cheapest_total += cheapest_cost

        comparisons.append(ComparisonItem(
            model=model,
            provider=provider,
            actual_cost=round(actual_cost, 6),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            alternatives=alternatives,
        ))

    return ComparisonResponse(
        comparisons=comparisons,
        current_total=round(current_total, 6),
        cheapest_total=round(cheapest_total, 6),
    )


# =============================================================================
# WEBHOOK ENDPOINTS
# =============================================================================


@app.post("/api/v1/webhooks", response_model=WebhookResponse, tags=["Webhooks"])
async def create_webhook(
    webhook_data: WebhookCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebhookResponse:
    """Register a webhook URL for budget alerts."""
    webhook = Webhook(
        user_id=current_user.id,
        url=webhook_data.url,
        event_type=webhook_data.event_type,
    )
    db.add(webhook)
    db.commit()
    db.refresh(webhook)

    return WebhookResponse(
        id=webhook.id,
        url=webhook.url,
        event_type=webhook.event_type,
        is_active=webhook.is_active,
        created_at=webhook.created_at,
    )


@app.get("/api/v1/webhooks", response_model=WebhookListResponse, tags=["Webhooks"])
async def list_webhooks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebhookListResponse:
    """List user's webhooks."""
    webhooks = db.query(Webhook).filter(
        Webhook.user_id == current_user.id,
        Webhook.is_active == True,
    ).all()

    return WebhookListResponse(
        webhooks=[
            WebhookResponse(
                id=w.id,
                url=w.url,
                event_type=w.event_type,
                is_active=w.is_active,
                created_at=w.created_at,
            )
            for w in webhooks
        ]
    )


@app.delete("/api/v1/webhooks/{webhook_id}", tags=["Webhooks"])
async def delete_webhook(
    webhook_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a webhook."""
    webhook = db.query(Webhook).filter(
        Webhook.id == webhook_id,
        Webhook.user_id == current_user.id,
    ).first()

    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    webhook.is_active = False
    db.commit()

    return {"success": True, "message": "Webhook deleted"}


# =============================================================================
# CACHE ENDPOINTS
# =============================================================================


@app.get("/api/v1/cache/stats", response_model=CacheStatsResponse, tags=["Cache"])
async def get_cache_stats(
    current_user: User = Depends(get_current_user),
) -> CacheStatsResponse:
    """Get cache statistics (hit rate, size, etc.)."""
    stats = response_cache.stats()
    return CacheStatsResponse(**stats)


@app.delete("/api/v1/cache", tags=["Cache"])
async def clear_cache(
    current_user: User = Depends(get_current_user),
):
    """Clear the response cache."""
    response_cache.clear()
    return {"success": True, "message": "Cache cleared"}


# =============================================================================
# USAGE LOGS EXPLORER
# =============================================================================


@app.get("/api/v1/logs", response_model=UsageLogsListResponse, tags=["Logs"])
@limiter.limit("60/minute")
async def get_logs(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Results per page"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    model: Optional[str] = Query(None, description="Filter by model"),
    tag: Optional[str] = Query(None, description="Filter by tag name"),
    cache_hit: Optional[bool] = Query(None, description="Filter by cache hit"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List usage logs with filtering, sorting, and pagination."""
    query = db.query(UsageLog).filter(UsageLog.user_id == current_user.id)

    # Apply filters
    if provider:
        query = query.filter(UsageLog.provider == provider)
    if model:
        query = query.filter(UsageLog.model == model)
    if cache_hit is not None:
        query = query.filter(UsageLog.cache_hit == cache_hit)
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from format. Use YYYY-MM-DD.")
        query = query.filter(UsageLog.created_at >= dt_from)
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_to format. Use YYYY-MM-DD.")
        query = query.filter(UsageLog.created_at < dt_to)
    if date_from and date_to:
        if datetime.strptime(date_from, "%Y-%m-%d") > datetime.strptime(date_to, "%Y-%m-%d"):
            raise HTTPException(status_code=400, detail="date_from must be before or equal to date_to.")
    if tag:
        query = query.join(UsageLog.tags).filter(Tag.name == tag)

    # Count total
    total = query.count()

    # Apply sorting (whitelist to prevent attribute access injection)
    ALLOWED_SORT_FIELDS = {
        "created_at": UsageLog.created_at,
        "cost_usd": UsageLog.cost_usd,
        "input_tokens": UsageLog.input_tokens,
        "output_tokens": UsageLog.output_tokens,
        "latency_ms": UsageLog.latency_ms,
        "provider": UsageLog.provider,
        "model": UsageLog.model,
    }
    sort_col = ALLOWED_SORT_FIELDS.get(sort_by, UsageLog.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    # Paginate
    offset = (page - 1) * page_size
    logs = query.offset(offset).limit(page_size).all()

    return UsageLogsListResponse(
        logs=[
            UsageLogResponse(
                id=log.id,
                provider=log.provider,
                model=log.model,
                input_tokens=log.input_tokens,
                output_tokens=log.output_tokens,
                cost_usd=log.cost_usd,
                latency_ms=log.latency_ms,
                cache_hit=log.cache_hit,
                tags=[t.name for t in log.tags],
                created_at=log.created_at,
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total,
    )


@app.get("/api/v1/logs/{log_id}", response_model=UsageLogResponse, tags=["Logs"])
async def get_log(
    log_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single usage log entry by ID."""
    log = db.query(UsageLog).filter(
        UsageLog.id == log_id,
        UsageLog.user_id == current_user.id,
    ).first()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log entry not found",
        )

    return UsageLogResponse(
        id=log.id,
        provider=log.provider,
        model=log.model,
        input_tokens=log.input_tokens,
        output_tokens=log.output_tokens,
        cost_usd=log.cost_usd,
        latency_ms=log.latency_ms,
        cache_hit=log.cache_hit,
        tags=[t.name for t in log.tags],
        created_at=log.created_at,
    )


# =============================================================================
# TAGS
# =============================================================================


@app.post("/api/v1/tags", response_model=TagResponse, tags=["Tags"])
@limiter.limit("30/minute")
async def create_tag(
    request: Request,
    tag_data: TagCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new tag."""
    # Check for duplicate name
    existing = db.query(Tag).filter(
        Tag.user_id == current_user.id,
        Tag.name == tag_data.name,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tag '{tag_data.name}' already exists",
        )

    tag = Tag(
        user_id=current_user.id,
        name=tag_data.name,
        color=tag_data.color,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)

    return TagResponse(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        usage_count=0,
        created_at=tag.created_at,
    )


@app.get("/api/v1/tags", response_model=TagListResponse, tags=["Tags"])
@limiter.limit("60/minute")
async def list_tags(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List user's tags with usage counts."""
    tags = db.query(Tag).filter(Tag.user_id == current_user.id).all()

    tag_responses = []
    for tag in tags:
        count = db.query(func.count(usage_log_tags.c.usage_log_id)).filter(
            usage_log_tags.c.tag_id == tag.id
        ).scalar() or 0

        tag_responses.append(TagResponse(
            id=tag.id,
            name=tag.name,
            color=tag.color,
            usage_count=count,
            created_at=tag.created_at,
        ))

    return TagListResponse(tags=tag_responses)


@app.delete("/api/v1/tags/{tag_id}", tags=["Tags"])
async def delete_tag(
    tag_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a tag."""
    tag = db.query(Tag).filter(
        Tag.id == tag_id,
        Tag.user_id == current_user.id,
    ).first()

    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found",
        )

    db.delete(tag)
    db.commit()
    return {"success": True, "message": "Tag deleted"}


@app.post("/api/v1/logs/{log_id}/tags", tags=["Tags"])
async def attach_tags(
    log_id: str,
    tag_data: TagAttach,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Attach tags to a usage log entry."""
    log = db.query(UsageLog).filter(
        UsageLog.id == log_id,
        UsageLog.user_id == current_user.id,
    ).first()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log entry not found",
        )

    for tag_id in tag_data.tag_ids:
        tag = db.query(Tag).filter(
            Tag.id == tag_id,
            Tag.user_id == current_user.id,
        ).first()
        if tag and tag not in log.tags:
            log.tags.append(tag)

    db.commit()
    return {"success": True, "message": "Tags attached"}


@app.delete("/api/v1/logs/{log_id}/tags/{tag_id}", tags=["Tags"])
async def detach_tag(
    log_id: str,
    tag_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a tag from a usage log entry."""
    log = db.query(UsageLog).filter(
        UsageLog.id == log_id,
        UsageLog.user_id == current_user.id,
    ).first()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log entry not found",
        )

    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if tag and tag in log.tags:
        log.tags.remove(tag)
        db.commit()

    return {"success": True, "message": "Tag removed"}


# =============================================================================
# DATA EXPORT
# =============================================================================


@app.get("/api/v1/export/csv", tags=["Export"])
@limiter.limit("10/minute")
async def export_csv(
    request: Request,
    provider: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export usage logs as CSV."""
    import csv
    import io

    query = db.query(UsageLog).filter(UsageLog.user_id == current_user.id)
    if provider:
        query = query.filter(UsageLog.provider == provider)
    if model:
        query = query.filter(UsageLog.model == model)
    if date_from:
        try:
            query = query.filter(UsageLog.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from format. Use YYYY-MM-DD.")
    if date_to:
        try:
            query = query.filter(UsageLog.created_at < datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_to format. Use YYYY-MM-DD.")
    if date_from and date_to:
        if datetime.strptime(date_from, "%Y-%m-%d") > datetime.strptime(date_to, "%Y-%m-%d"):
            raise HTTPException(status_code=400, detail="date_from must be before or equal to date_to.")
    if tag:
        query = query.join(UsageLog.tags).filter(Tag.name == tag)

    logs = query.order_by(UsageLog.created_at.desc()).all()

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "created_at", "provider", "model", "input_tokens", "output_tokens",
                         "cost_usd", "latency_ms", "cache_hit", "tags"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for log in logs:
            tag_names = ",".join(t.name for t in log.tags)
            writer.writerow([
                log.id,
                log.created_at.isoformat(),
                log.provider,
                log.model,
                log.input_tokens,
                log.output_tokens,
                round(log.cost_usd, 6),
                round(log.latency_ms, 2) if log.latency_ms else "",
                log.cache_hit,
                tag_names,
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    now = datetime.utcnow().strftime("%Y-%m-%d")
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=llmlab_export_{now}.csv"},
    )


@app.get("/api/v1/export/json", tags=["Export"])
@limiter.limit("10/minute")
async def export_json(
    request: Request,
    provider: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export usage logs as JSON."""
    query = db.query(UsageLog).filter(UsageLog.user_id == current_user.id)
    if provider:
        query = query.filter(UsageLog.provider == provider)
    if model:
        query = query.filter(UsageLog.model == model)
    if date_from:
        try:
            query = query.filter(UsageLog.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from format. Use YYYY-MM-DD.")
    if date_to:
        try:
            query = query.filter(UsageLog.created_at < datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_to format. Use YYYY-MM-DD.")
    if date_from and date_to:
        if datetime.strptime(date_from, "%Y-%m-%d") > datetime.strptime(date_to, "%Y-%m-%d"):
            raise HTTPException(status_code=400, detail="date_from must be before or equal to date_to.")
    if tag:
        query = query.join(UsageLog.tags).filter(Tag.name == tag)

    logs = query.order_by(UsageLog.created_at.desc()).all()

    data = {
        "exported_at": datetime.utcnow().isoformat(),
        "total_logs": len(logs),
        "total_cost_usd": round(sum(l.cost_usd for l in logs), 6),
        "logs": [
            {
                "id": log.id,
                "created_at": log.created_at.isoformat(),
                "provider": log.provider,
                "model": log.model,
                "input_tokens": log.input_tokens,
                "output_tokens": log.output_tokens,
                "cost_usd": round(log.cost_usd, 6),
                "latency_ms": round(log.latency_ms, 2) if log.latency_ms else None,
                "cache_hit": log.cache_hit,
                "tags": [t.name for t in log.tags],
            }
            for log in logs
        ],
    }

    now = datetime.utcnow().strftime("%Y-%m-%d")
    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=llmlab_export_{now}.json"},
    )


# =============================================================================
# COST FORECASTING
# =============================================================================


@app.get("/api/v1/stats/forecast", response_model=ForecastResponse, tags=["Stats"])
@limiter.limit("30/minute")
async def get_forecast(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Forecast next month's costs based on historical trends."""
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)

    # Get daily costs for last 30 days
    logs = db.query(UsageLog).filter(
        UsageLog.user_id == current_user.id,
        UsageLog.created_at >= thirty_days_ago,
    ).all()

    if not logs:
        return ForecastResponse(
            predicted_next_month_usd=0.0,
            daily_average_usd=0.0,
            trend="stable",
            trend_pct_change=0.0,
            confidence="low",
            projected_daily=[],
        )

    # Aggregate by day
    daily_costs: dict[str, float] = {}
    for log in logs:
        day_key = log.created_at.strftime("%Y-%m-%d")
        daily_costs[day_key] = daily_costs.get(day_key, 0) + log.cost_usd

    # Fill in missing days with 0
    daily_values = []
    for i in range(30):
        day = (thirty_days_ago + timedelta(days=i)).strftime("%Y-%m-%d")
        daily_values.append(daily_costs.get(day, 0.0))

    n = len(daily_values)
    daily_avg = sum(daily_values) / n if n > 0 else 0.0

    # Linear regression: y = mx + b
    x_mean = (n - 1) / 2.0
    y_mean = daily_avg
    numerator = sum((i - x_mean) * (daily_values[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    slope = numerator / denominator if denominator != 0 else 0.0
    intercept = y_mean - slope * x_mean

    # Project 30 days forward
    projected_daily = []
    projected_total = 0.0
    for i in range(30):
        projected_cost = max(0.0, slope * (n + i) + intercept)
        projected_total += projected_cost
        future_date = (now + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        projected_daily.append(DailyCost(date=future_date, cost_usd=round(projected_cost, 6), call_count=0))

    # Determine trend
    first_half_avg = sum(daily_values[:15]) / 15 if n >= 15 else daily_avg
    second_half_avg = sum(daily_values[15:]) / 15 if n >= 15 else daily_avg
    pct_change = ((second_half_avg - first_half_avg) / first_half_avg * 100) if first_half_avg > 0 else 0.0

    if pct_change > 10:
        trend = "increasing"
    elif pct_change < -10:
        trend = "decreasing"
    else:
        trend = "stable"

    # Confidence based on data density
    days_with_data = sum(1 for v in daily_values if v > 0)
    if days_with_data >= 20:
        confidence = "high"
    elif days_with_data >= 10:
        confidence = "medium"
    else:
        confidence = "low"

    return ForecastResponse(
        predicted_next_month_usd=round(projected_total, 4),
        daily_average_usd=round(daily_avg, 6),
        trend=trend,
        trend_pct_change=round(pct_change, 2),
        confidence=confidence,
        projected_daily=projected_daily,
    )


# =============================================================================
# ANOMALY DETECTION
# =============================================================================


@app.get("/api/v1/stats/anomalies", response_model=AnomalyResponse, tags=["Stats"])
@limiter.limit("30/minute")
async def get_anomalies(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get recent anomaly events for the current user."""
    anomalies = detect_anomalies(current_user.id, db)
    has_active = any(a.severity in ("warning", "critical") for a in anomalies)
    return AnomalyResponse(anomalies=anomalies, has_active_anomaly=has_active)


# =============================================================================
# RUN SERVER
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
