"""Add DailyReport table and Department.row_no

Revision ID: 20260521_v2_add_daily_report
Revises: 20260521_add_date_of_admission_bed_capacity
Create Date: 2026-05-21 00:00:00.000000

Adds:
  - daily_reports table (Форма 007/о — щоденний листок обліку руху хворих)
  - departments.row_no (Integer, nullable) — МОЗ нумерація рядка у Формі 007

"""
from alembic import op
import sqlalchemy as sa


revision = '20260521_v2_add_daily_report'
down_revision = '20260521_add_date_of_admission_bed_capacity'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'daily_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('report_date', sa.Date(), nullable=False),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('departments.id'), nullable=False),
        sa.Column('beds_total', sa.Integer(), nullable=True),
        sa.Column('beds_renovation', sa.Integer(), nullable=True),
        sa.Column('patients_start', sa.Integer(), nullable=True),
        sa.Column('admitted_total', sa.Integer(), nullable=True),
        sa.Column('admitted_rural', sa.Integer(), nullable=True),
        sa.Column('admitted_children', sa.Integer(), nullable=True),
        sa.Column('transferred_in', sa.Integer(), nullable=True),
        sa.Column('transferred_out', sa.Integer(), nullable=True),
        sa.Column('discharged_total', sa.Integer(), nullable=True),
        sa.Column('discharged_to_other', sa.Integer(), nullable=True),
        sa.Column('deaths', sa.Integer(), nullable=True),
        sa.Column('patients_end', sa.Integer(), nullable=True),
        sa.Column('patients_end_rural', sa.Integer(), nullable=True),
        sa.Column('mothers_with_children', sa.Integer(), nullable=True),
        sa.Column('free_male', sa.Integer(), nullable=True),
        sa.Column('free_female', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('report_date', 'department_id', name='uq_daily_report_date_dept'),
    )
    op.create_index('idx_daily_report_date', 'daily_reports', ['report_date'])

    with op.batch_alter_table('departments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('row_no', sa.Integer(), nullable=True))


def downgrade():
    op.drop_index('idx_daily_report_date', table_name='daily_reports')
    op.drop_table('daily_reports')

    with op.batch_alter_table('departments', schema=None) as batch_op:
        batch_op.drop_column('row_no')
