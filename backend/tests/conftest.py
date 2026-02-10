"""
Pytest fixtures and configuration for LLMLab tests.

Sets up test database, test client, and mock data.
"""

import os
from datetime import datetime, timedelta
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment variables BEFORE importing app modules
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-jwt-secret-key-for-testing-only"
os.environ["ENCRYPTION_KEY"] = "RwW3L0xvSoW8IcxrPCGZ2DC3RL9ATh6YNZpbYo72Hsw="  # Valid Fernet key
os.environ["GITHUB_CLIENT_ID"] = "test-client-id"
os.environ["GITHUB_CLIENT_SECRET"] = "test-client-secret"
os.environ["GITHUB_REDIRECT_URI"] = "http://localhost:8000/auth/github/callback"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["ENVIRONMENT"] = "test"

# Clear settings cache so env vars above take effect even if config was imported earlier
from config import get_settings
get_settings.cache_clear()

from database import Base, get_db
from main import app
from models import ApiKey, Budget, Tag, UsageLog, User, Webhook
from security import encrypt_api_key


# =============================================================================
# DATABASE FIXTURES
# =============================================================================


@pytest.fixture(scope="function")
def db_engine():
    """Create a test database engine with SQLite in-memory."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a database session for testing."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Create a test client with overridden database dependency."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =============================================================================
# USER FIXTURES
# =============================================================================


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        github_id=12345,
        email="test@example.com",
        username="testuser",
        avatar_url="https://github.com/images/test.png",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_user_token(test_user: User) -> str:
    """Generate a JWT token for the test user."""
    from auth import create_access_token

    token, _ = create_access_token(test_user.id)
    return token


@pytest.fixture
def auth_headers(test_user_token: str) -> dict:
    """Headers with authentication for test requests."""
    return {"Authorization": f"Bearer {test_user_token}"}


# =============================================================================
# API KEY FIXTURES
# =============================================================================


@pytest.fixture
def test_openai_key(db_session: Session, test_user: User) -> ApiKey:
    """Create a test OpenAI API key."""
    encrypted = encrypt_api_key("sk-test-openai-key-12345")
    api_key = ApiKey(
        user_id=test_user.id,
        provider="openai",
        encrypted_key=encrypted,
        proxy_key="llmlab_pk_test_openai_12345678",
    )
    db_session.add(api_key)
    db_session.commit()
    db_session.refresh(api_key)
    return api_key


@pytest.fixture
def test_anthropic_key(db_session: Session, test_user: User) -> ApiKey:
    """Create a test Anthropic API key."""
    encrypted = encrypt_api_key("sk-ant-test-anthropic-key-12345")
    api_key = ApiKey(
        user_id=test_user.id,
        provider="anthropic",
        encrypted_key=encrypted,
        proxy_key="llmlab_pk_test_anthropic_12345",
    )
    db_session.add(api_key)
    db_session.commit()
    db_session.refresh(api_key)
    return api_key


# =============================================================================
# USAGE LOG FIXTURES
# =============================================================================


@pytest.fixture
def test_usage_logs(db_session: Session, test_user: User) -> list[UsageLog]:
    """Create sample usage logs for testing stats."""
    logs = []
    now = datetime.utcnow()

    # Today's logs
    logs.append(
        UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0075,
            latency_ms=450.5,
            cache_hit=False,
            created_at=now,
        )
    )

    # Yesterday's logs
    logs.append(
        UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=2000,
            output_tokens=1000,
            cost_usd=0.0009,
            latency_ms=120.3,
            cache_hit=False,
            created_at=now - timedelta(days=1),
        )
    )

    # Last week's logs
    logs.append(
        UsageLog(
            user_id=test_user.id,
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            input_tokens=5000,
            output_tokens=2000,
            cost_usd=0.045,
            latency_ms=890.1,
            cache_hit=False,
            created_at=now - timedelta(days=5),
        )
    )

    # Last month's logs
    logs.append(
        UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=10000,
            output_tokens=5000,
            cost_usd=0.075,
            latency_ms=1200.0,
            cache_hit=False,
            created_at=now - timedelta(days=20),
        )
    )

    # Cache hit log (cost=0, latency=0)
    logs.append(
        UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0,
            latency_ms=0.0,
            cache_hit=True,
            created_at=now - timedelta(hours=2),
        )
    )

    for log in logs:
        db_session.add(log)
    db_session.commit()

    return logs


# =============================================================================
# BUDGET FIXTURES
# =============================================================================


@pytest.fixture
def test_budget(db_session: Session, test_user: User) -> Budget:
    """Create a test budget."""
    budget = Budget(
        user_id=test_user.id,
        amount_usd=100.0,
        period="monthly",
        alert_threshold=80.0,
    )
    db_session.add(budget)
    db_session.commit()
    db_session.refresh(budget)
    return budget


# =============================================================================
# WEBHOOK FIXTURES
# =============================================================================


@pytest.fixture
def test_webhook(db_session: Session, test_user: User) -> Webhook:
    """Create a test webhook."""
    webhook = Webhook(
        user_id=test_user.id,
        url="https://example.com/webhook",
        event_type="budget_warning",
    )
    db_session.add(webhook)
    db_session.commit()
    db_session.refresh(webhook)
    return webhook


# =============================================================================
# TAG FIXTURES
# =============================================================================


@pytest.fixture
def test_tags(db_session: Session, test_user: User) -> list[Tag]:
    """Create sample tags for testing."""
    tags = [
        Tag(user_id=test_user.id, name="backend", color="#3b82f6"),
        Tag(user_id=test_user.id, name="production", color="#ef4444"),
        Tag(user_id=test_user.id, name="feature-x", color="#10b981"),
    ]
    for tag in tags:
        db_session.add(tag)
    db_session.commit()
    for tag in tags:
        db_session.refresh(tag)
    return tags


@pytest.fixture
def test_tagged_logs(
    db_session: Session, test_user: User, test_usage_logs: list[UsageLog], test_tags: list[Tag]
) -> list[UsageLog]:
    """Attach tags to some usage logs."""
    # Attach 'backend' tag to first log
    test_usage_logs[0].tags.append(test_tags[0])
    # Attach 'production' tag to first and second logs
    test_usage_logs[0].tags.append(test_tags[1])
    test_usage_logs[1].tags.append(test_tags[1])
    db_session.commit()
    return test_usage_logs
