"""Add is_urgent and history_submitted to records

Revision ID: 20260612_record_urgency
Revises: 20260611_status_scopes
Create Date: 2026-06-12

"""
from alembic import op
import sqlalchemy as sa


revision = '20260612_record_urgency'
down_revision = '20260611_status_scopes'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_urgent', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('history_submitted', sa.Boolean(), server_default='0', nullable=False))
        batch_op.create_index('idx_record_is_urgent', ['is_urgent'])
        batch_op.create_index('idx_record_history_submitted', ['history_submitted'])


def downgrade():
    with op.batch_alter_table('records', schema=None) as batch_op:
        batch_op.drop_index('idx_record_history_submitted')
        batch_op.drop_index('idx_record_is_urgent')
        batch_op.drop_column('history_submitted')
        batch_op.drop_column('is_urgent')
