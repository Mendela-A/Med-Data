"""print_settings_dept_title

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-25

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('print_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('form007_dept_title', sa.String(200), nullable=False,
                                      server_default='Рух хворих і ліжкового фонду'))

    op.execute(
        "UPDATE print_settings SET "
        "form007_dept_title = 'Рух хворих і ліжкового фонду' "
        "WHERE id = 1"
    )


def downgrade():
    with op.batch_alter_table('print_settings', schema=None) as batch_op:
        batch_op.drop_column('form007_dept_title')
