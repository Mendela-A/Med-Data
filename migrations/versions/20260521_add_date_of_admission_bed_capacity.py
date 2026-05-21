"""Add date_of_admission to records, bed_capacity to departments

Revision ID: 20260521_add_date_of_admission_bed_capacity
Revises: 20260330_add_department_fk
Create Date: 2026-05-21 00:00:00.000000

Adds:
  - records.date_of_admission (Date, nullable, indexed) — used for Form 007 admission tracking
  - departments.bed_capacity (Integer, nullable) — used for Form 016 occupancy/turnover indicators

"""
from alembic import op
import sqlalchemy as sa


revision = '20260521_add_date_of_admission_bed_capacity'
down_revision = '20260330_add_department_fk'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('date_of_admission', sa.Date(), nullable=True))
        batch_op.create_index('idx_record_date_of_admission', ['date_of_admission'])

    with op.batch_alter_table('departments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bed_capacity', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('records', schema=None) as batch_op:
        batch_op.drop_index('idx_record_date_of_admission')
        batch_op.drop_column('date_of_admission')

    with op.batch_alter_table('departments', schema=None) as batch_op:
        batch_op.drop_column('bed_capacity')
