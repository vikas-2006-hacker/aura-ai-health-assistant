"""create health data

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_data",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric_type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_health_data_user_id", "health_data", ["user_id"])
    op.create_index("ix_health_data_metric_type", "health_data", ["metric_type"])
    op.create_index("ix_health_data_recorded_at", "health_data", ["recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_health_data_recorded_at", table_name="health_data")
    op.drop_index("ix_health_data_metric_type", table_name="health_data")
    op.drop_index("ix_health_data_user_id", table_name="health_data")
    op.drop_table("health_data")
