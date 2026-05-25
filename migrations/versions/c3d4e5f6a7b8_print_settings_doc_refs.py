"""print_settings_doc_refs

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-25

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('print_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('form007_form_no', sa.String(50), nullable=False,
                                      server_default='Форма № 007/о'))
        batch_op.add_column(sa.Column('form007_decree', sa.String(200), nullable=False,
                                      server_default='Затверджено наказом МОЗ України від 29.05.2013 р. № 110'))
        batch_op.add_column(sa.Column('form016_form_no', sa.String(50), nullable=False,
                                      server_default='Форма № 016/о'))
        batch_op.add_column(sa.Column('form016_decree', sa.String(200), nullable=False,
                                      server_default='Затверджено наказом МОЗ України від 27.12.05 р. № 760'))

    op.execute(
        "UPDATE print_settings SET "
        "form007_form_no  = 'Форма № 007/о', "
        "form007_decree   = 'Затверджено наказом МОЗ України від 29.05.2013 р. № 110', "
        "form016_form_no  = 'Форма № 016/о', "
        "form016_decree   = 'Затверджено наказом МОЗ України від 27.12.05 р. № 760' "
        "WHERE id = 1"
    )


def downgrade():
    with op.batch_alter_table('print_settings', schema=None) as batch_op:
        batch_op.drop_column('form016_decree')
        batch_op.drop_column('form016_form_no')
        batch_op.drop_column('form007_decree')
        batch_op.drop_column('form007_form_no')
