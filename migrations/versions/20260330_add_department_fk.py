"""Add department_id FK to records table

Revision ID: 20260330_add_department_fk
Revises: 20260330_add_composite_indexes
Create Date: 2026-03-30 00:00:00.000000

Adds a nullable department_id column with FK to departments.id.
Populates it from the existing discharge_department text field.
The discharge_department column is kept for backwards compatibility.

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '20260330_add_department_fk'
down_revision = '20260330_add_composite_indexes'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('department_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_records_department_id', 'departments', ['department_id'], ['id'])
        batch_op.create_index('idx_record_department_id', ['department_id'])

    # Data migration: populate department_id from discharge_department text
    conn = op.get_bind()
    conn.execute(text("""
        UPDATE records
        SET department_id = (
            SELECT d.id FROM departments d
            WHERE d.name = records.discharge_department
            LIMIT 1
        )
        WHERE discharge_department IS NOT NULL
    """))


def downgrade():
    with op.batch_alter_table('records', schema=None) as batch_op:
        batch_op.drop_index('idx_record_department_id')
        batch_op.drop_constraint('fk_records_department_id', type_='foreignkey')
        batch_op.drop_column('department_id')
