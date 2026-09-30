"""create water intake

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'water_intakes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount_ml', sa.Integer(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_water_intakes_user_id', 'water_intakes', ['user_id'])
    op.create_index('ix_water_intakes_consumed_at', 'water_intakes', ['consumed_at'])


def downgrade() -> None:
    op.drop_index('ix_water_intakes_consumed_at', table_name='water_intakes')
    op.drop_index('ix_water_intakes_user_id', table_name='water_intakes')
    op.drop_table('water_intakes')
