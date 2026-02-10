"""Initial schema - users, api_keys, usage_logs, budgets, webhooks, tags

Revision ID: 001
Revises: None
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("github_id", sa.Integer(), unique=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
    )
    op.create_index("ix_users_github_id", "users", ["github_id"])
    op.create_index("ix_users_email", "users", ["email"])

    # API Keys table
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("proxy_key", sa.String(50), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_provider", "api_keys", ["provider"])
    op.create_index("ix_api_keys_proxy_key", "api_keys", ["proxy_key"])

    # Usage Logs table
    op.create_table(
        "usage_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), default=0, nullable=False),
        sa.Column("output_tokens", sa.Integer(), default=0, nullable=False),
        sa.Column("cost_usd", sa.Float(), default=0.0, nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), default=False, nullable=False),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_usage_logs_user_id", "usage_logs", ["user_id"])
    op.create_index("ix_usage_logs_provider", "usage_logs", ["provider"])
    op.create_index("ix_usage_logs_model", "usage_logs", ["model"])
    op.create_index("ix_usage_logs_cost_usd", "usage_logs", ["cost_usd"])
    op.create_index("ix_usage_logs_created_at", "usage_logs", ["created_at"])
    op.create_index("idx_usage_logs_user_created", "usage_logs", ["user_id", "created_at"])
    op.create_index(
        "idx_usage_logs_user_provider_created",
        "usage_logs",
        ["user_id", "provider", "created_at"],
    )

    # Budgets table
    op.create_table(
        "budgets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("period", sa.String(20), default="monthly", nullable=False),
        sa.Column("alert_threshold", sa.Float(), default=80.0, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_budgets_user_id", "budgets", ["user_id"])

    # Webhooks table
    op.create_table(
        "webhooks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_webhooks_user_id", "webhooks", ["user_id"])

    # Tags table
    op.create_table(
        "tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(7), default="#6366f1", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tags_user_id", "tags", ["user_id"])

    # Usage Log Tags junction table (many-to-many)
    op.create_table(
        "usage_log_tags",
        sa.Column(
            "usage_log_id",
            sa.String(36),
            sa.ForeignKey("usage_logs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.String(36),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("usage_log_tags")
    op.drop_table("tags")
    op.drop_table("webhooks")
    op.drop_table("budgets")
    op.drop_table("usage_logs")
    op.drop_table("api_keys")
    op.drop_table("users")
