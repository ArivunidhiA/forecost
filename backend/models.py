"""
SQLAlchemy ORM models for LLMLab.

Tables:
- users: GitHub-authenticated users
- api_keys: Encrypted provider API keys with proxy keys
- usage_logs: Token usage, cost, and latency tracking
- budgets: Monthly spending budgets
- webhooks: Budget alert webhook URLs
- tags: User-defined tags for cost attribution
- usage_log_tags: Junction table for log-tag many-to-many
"""

import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Table, Text
from sqlalchemy.orm import relationship

from database import Base


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def generate_proxy_key() -> str:
    """
    Generate a unique proxy key for API access.

    Format: llmlab_pk_{32 random hex chars}
    """
    return f"llmlab_pk_{secrets.token_hex(16)}"


class User(Base):
    """
    User account authenticated via GitHub OAuth.

    Attributes:
        id: Unique identifier (UUID)
        github_id: GitHub user ID (unique)
        email: User's email from GitHub
        username: GitHub username
        avatar_url: GitHub profile picture URL
        created_at: Account creation timestamp
        is_active: Whether account is active
    """

    __tablename__ = "users"

    id: str = Column(String(36), primary_key=True, default=generate_uuid)
    github_id: int = Column(Integer, unique=True, nullable=False, index=True)
    email: str = Column(String(255), nullable=False, index=True)
    username: Optional[str] = Column(String(255), nullable=True)
    avatar_url: Optional[str] = Column(String(500), nullable=True)
    created_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    is_active: bool = Column(Boolean, default=True, nullable=False)

    # Relationships
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    usage_logs = relationship("UsageLog", back_populates="user", cascade="all, delete-orphan")
    budgets = relationship("Budget", back_populates="user", cascade="all, delete-orphan")
    webhooks = relationship("Webhook", back_populates="user", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="user", cascade="all, delete-orphan")


class ApiKey(Base):
    """
    Encrypted API key for a provider.

    Users store their real API keys (encrypted), and receive a proxy key
    that they use in their applications. LLMLab intercepts requests and
    uses the real key to forward to the provider.

    Attributes:
        id: Unique identifier (UUID)
        user_id: Foreign key to users
        provider: Provider name (openai, anthropic)
        encrypted_key: Fernet-encrypted real API key
        proxy_key: Unique key user uses in their apps
        created_at: Creation timestamp
        last_used_at: Last usage timestamp
        is_active: Whether key is active
    """

    __tablename__ = "api_keys"

    id: str = Column(String(36), primary_key=True, default=generate_uuid)
    user_id: str = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: str = Column(String(50), nullable=False, index=True)
    encrypted_key: str = Column(Text, nullable=False)
    proxy_key: str = Column(String(50), unique=True, nullable=False, index=True, default=generate_proxy_key)
    created_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_used_at: Optional[datetime] = Column(DateTime, nullable=True)
    is_active: bool = Column(Boolean, default=True, nullable=False)

    # Relationships
    user = relationship("User", back_populates="api_keys")


class UsageLog(Base):
    """
    Log of API usage for cost tracking.

    Every proxied request logs tokens and calculated cost.

    Attributes:
        id: Unique identifier (UUID)
        user_id: Foreign key to users
        provider: Provider name (openai, anthropic)
        model: Model name used
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens
        cost_usd: Calculated cost in USD
        request_id: Optional request ID for tracing
        created_at: Timestamp of the request
    """

    __tablename__ = "usage_logs"
    __table_args__ = (
        Index("idx_usage_logs_user_created", "user_id", "created_at"),
        Index("idx_usage_logs_user_provider_created", "user_id", "provider", "created_at"),
    )

    id: str = Column(String(36), primary_key=True, default=generate_uuid)
    user_id: str = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: str = Column(String(50), nullable=False, index=True)
    model: str = Column(String(100), nullable=False, index=True)
    input_tokens: int = Column(Integer, default=0, nullable=False)
    output_tokens: int = Column(Integer, default=0, nullable=False)
    cost_usd: float = Column(Float, default=0.0, nullable=False, index=True)
    latency_ms: Optional[float] = Column(Float, nullable=True)
    cache_hit: bool = Column(Boolean, default=False, nullable=False)
    request_id: Optional[str] = Column(String(100), nullable=True)
    created_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="usage_logs")
    tags = relationship("Tag", secondary="usage_log_tags", back_populates="usage_logs")


class Budget(Base):
    """
    Monthly spending budget for a user.

    Attributes:
        id: Unique identifier (UUID)
        user_id: Foreign key to users
        amount_usd: Monthly budget amount in USD
        period: Budget period (monthly)
        alert_threshold: Percentage at which to alert (default 80%)
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "budgets"

    id: str = Column(String(36), primary_key=True, default=generate_uuid)
    user_id: str = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_usd: float = Column(Float, nullable=False)
    period: str = Column(String(20), default="monthly", nullable=False)
    alert_threshold: float = Column(Float, default=80.0, nullable=False)
    created_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="budgets")


class Webhook(Base):
    """
    Webhook for budget alerts and anomaly notifications.

    Attributes:
        id: Unique identifier (UUID)
        user_id: Foreign key to users
        url: Webhook URL to POST to
        event_type: Event type (budget_warning, budget_exceeded, anomaly)
        is_active: Whether webhook is active
        created_at: Creation timestamp
    """

    __tablename__ = "webhooks"

    id: str = Column(String(36), primary_key=True, default=generate_uuid)
    user_id: str = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    url: str = Column(String(500), nullable=False)
    event_type: str = Column(String(50), nullable=False)
    is_active: bool = Column(Boolean, default=True, nullable=False)
    created_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="webhooks")


# =============================================================================
# TAGS (Many-to-Many with UsageLog)
# =============================================================================

usage_log_tags = Table(
    "usage_log_tags",
    Base.metadata,
    Column("usage_log_id", String(36), ForeignKey("usage_logs.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    """
    User-defined tag for cost attribution and filtering.

    Tags can be attached to usage logs to group costs by project,
    feature, environment, or any custom dimension.

    Attributes:
        id: Unique identifier (UUID)
        user_id: Foreign key to users
        name: Tag name (e.g., "backend", "prod", "feature-x")
        color: Hex color for UI display
        created_at: Creation timestamp
    """

    __tablename__ = "tags"

    id: str = Column(String(36), primary_key=True, default=generate_uuid)
    user_id: str = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: str = Column(String(100), nullable=False)
    color: str = Column(String(7), default="#6366f1", nullable=False)
    created_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="tags")
    usage_logs = relationship("UsageLog", secondary="usage_log_tags", back_populates="tags")
