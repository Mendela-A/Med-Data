"""Add extra_permissions to users

Revision ID: 20260604_add_extra_permissions
Revises: f0e1d2c3b4a5
Create Date: 2026-06-04

"""
from alembic import op
import sqlalchemy as sa


revision = '20260604_add_extra_permissions'
down_revision = 'f0e1d2c3b4a5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('extra_permissions', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('extra_permissions')
