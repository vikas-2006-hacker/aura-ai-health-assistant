"""add wellness notification preference

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_preferences",
        sa.Column(
            "wellness_notifications",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("notification_preferences", "wellness_notifications")
