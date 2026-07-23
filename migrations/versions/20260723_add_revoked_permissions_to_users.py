"""Add revoked_permissions to users

Revision ID: 20260723_add_revoked_permissions
Revises: 20260702_merge_heads
Create Date: 2026-07-23

"""
from alembic import op
import sqlalchemy as sa


revision = '20260723_add_revoked_permissions'
down_revision = '20260702_merge_heads'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('revoked_permissions', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('revoked_permissions')
