"""Add indexes to audit_logs table

Revision ID: 20260330_add_audit_indexes
Revises: 20260321_add_adsj_suma
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '20260330_add_audit_indexes'
down_revision = '20260321_add_adsj_suma'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('idx_audit_created_at', 'audit_logs', ['created_at'])
    op.create_index('idx_audit_actor_id', 'audit_logs', ['actor_id'])
    op.create_index('idx_audit_action', 'audit_logs', ['action'])


def downgrade():
    op.drop_index('idx_audit_action', table_name='audit_logs')
    op.drop_index('idx_audit_actor_id', table_name='audit_logs')
    op.drop_index('idx_audit_created_at', table_name='audit_logs')
