"""Add composite indexes and history index to records table

Revision ID: 20260330_add_composite_indexes
Revises: 20260330_add_audit_indexes
Create Date: 2026-03-30 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '20260330_add_composite_indexes'
down_revision = '20260330_add_audit_indexes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('idx_record_date_dept', 'records', ['date_of_discharge', 'discharge_department'])
    op.create_index('idx_record_date_status', 'records', ['date_of_discharge', 'discharge_status'])
    op.create_index('idx_record_history', 'records', ['history'])


def downgrade():
    op.drop_index('idx_record_history', table_name='records')
    op.drop_index('idx_record_date_status', table_name='records')
    op.drop_index('idx_record_date_dept', table_name='records')
