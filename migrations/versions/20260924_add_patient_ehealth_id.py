"""Add patient_ehealth_id (ID пацієнта в ЕСОЗ) to records

Revision ID: 20260924_add_patient_ehealth_id
Revises: 20260723_add_revoked_permissions
Create Date: 2026-09-24

"""
from alembic import op
import sqlalchemy as sa


revision = '20260924_add_patient_ehealth_id'
down_revision = '20260723_add_revoked_permissions'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('patient_ehealth_id', sa.String(length=36), nullable=True))
    # Унікальний на кожен запис; NULL-и (ID не вказано) дозволені у будь-якій кількості
    op.create_index('uq_record_patient_ehealth_id', 'records', ['patient_ehealth_id'], unique=True)


def downgrade():
    op.drop_index('uq_record_patient_ehealth_id', table_name='records')
    with op.batch_alter_table('records', schema=None) as batch_op:
        batch_op.drop_column('patient_ehealth_id')
