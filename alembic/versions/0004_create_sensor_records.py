"""create normalized sensor records

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sensor_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_platform", sa.String(length=50), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("data_type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("start_time", sa.DateTime(), nullable=False),
        sa.Column("end_time", sa.DateTime(), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("device_id", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("validation_status", sa.String(length=20), nullable=False, server_default="valid"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", "source_platform", "source_record_id", name="uq_sensor_records_source_identity"),
        sa.UniqueConstraint("user_id", "source_platform", "idempotency_key", name="uq_sensor_records_idempotency_key"),
    )
    op.create_index("ix_sensor_records_user_id", "sensor_records", ["user_id"])
    op.create_index("ix_sensor_records_data_type", "sensor_records", ["data_type"])
    op.create_index("ix_sensor_records_start_time", "sensor_records", ["start_time"])
    op.create_index("ix_sensor_records_user_start_time", "sensor_records", ["user_id", "start_time"])

    op.create_table(
        "sensor_sync_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_platform", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_sensor_sync_records_user_id", "sensor_sync_records", ["user_id"])
    op.create_index("ix_sensor_sync_records_created_at", "sensor_sync_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sensor_sync_records_created_at", table_name="sensor_sync_records")
    op.drop_index("ix_sensor_sync_records_user_id", table_name="sensor_sync_records")
    op.drop_table("sensor_sync_records")
    op.drop_index("ix_sensor_records_user_start_time", table_name="sensor_records")
    op.drop_index("ix_sensor_records_start_time", table_name="sensor_records")
    op.drop_index("ix_sensor_records_data_type", table_name="sensor_records")
    op.drop_index("ix_sensor_records_user_id", table_name="sensor_records")
    op.drop_table("sensor_records")
