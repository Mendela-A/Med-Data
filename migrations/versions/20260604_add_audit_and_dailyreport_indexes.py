"""add audit indexes and daily_report department_id index

Revision ID: 20260604_indexes
Revises: f0e1d2c3b4a5
Create Date: 2026-06-04
"""
from alembic import op

revision = '20260604_indexes'
down_revision = '20260604_add_extra_permissions'
branch_labels = None
depends_on = None


def upgrade():
    # Audit table: no indexes existed — add four for common filter columns
    op.create_index('idx_audit_actor_id',    'audit_logs', ['actor_id'],    unique=False)
    op.create_index('idx_audit_created_at',  'audit_logs', ['created_at'],  unique=False)
    op.create_index('idx_audit_action',      'audit_logs', ['action'],      unique=False)
    op.create_index('idx_audit_target_type', 'audit_logs', ['target_type'], unique=False)

    # DailyReport: existing composite (report_date, department_id) starts with
    # report_date, so queries filtering by department_id first can't use it.
    op.create_index('idx_daily_report_department_id', 'daily_reports', ['department_id'], unique=False)


def downgrade():
    op.drop_index('idx_daily_report_department_id', table_name='daily_reports')
    op.drop_index('idx_audit_target_type', table_name='audit_logs')
    op.drop_index('idx_audit_action',      table_name='audit_logs')
    op.drop_index('idx_audit_created_at',  table_name='audit_logs')
    op.drop_index('idx_audit_actor_id',    table_name='audit_logs')
