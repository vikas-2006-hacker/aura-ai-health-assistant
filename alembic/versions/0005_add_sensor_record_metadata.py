"""add metadata to normalized sensor records

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sensor_records", sa.Column("metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sensor_records", "metadata")