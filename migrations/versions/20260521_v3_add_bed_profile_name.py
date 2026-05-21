"""Add bed_profile_name to Department

Revision ID: 20260521_v3_add_bed_profile_name
Revises: 20260521_v2_add_daily_report
Create Date: 2026-05-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '20260521_v3_add_bed_profile_name'
down_revision = '20260521_v2_add_daily_report'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('departments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bed_profile_name', sa.String(length=200), nullable=True))


def downgrade():
    with op.batch_alter_table('departments', schema=None) as batch_op:
        batch_op.drop_column('bed_profile_name')
