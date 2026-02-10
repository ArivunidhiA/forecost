"""Add fired_alerts table for persistent alert deduplication

Revision ID: 002
Revises: 001
Create Date: 2024-02-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fired_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("budget_id", sa.String(36), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_fired_alerts_user_id", "fired_alerts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_fired_alerts_user_id", table_name="fired_alerts")
    op.drop_table("fired_alerts")
