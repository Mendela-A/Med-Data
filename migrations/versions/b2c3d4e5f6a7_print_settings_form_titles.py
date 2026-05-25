"""print_settings_form_titles

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-25

"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('print_settings') as batch_op:
        batch_op.add_column(sa.Column('form007_title',    sa.String(200), nullable=False,
                                      server_default='ЛИСТОК ОБЛІКУ РУХУ ХВОРИХ'))
        batch_op.add_column(sa.Column('form007_subtitle', sa.String(200), nullable=False,
                                      server_default='і ліжкового фонду стаціонару'))
        batch_op.add_column(sa.Column('form016_title',    sa.String(200), nullable=False,
                                      server_default='ЗВЕДЕНА ВІДОМІСТЬ ОБЛІКУ РУХУ ХВОРИХ'))
        batch_op.add_column(sa.Column('form016_subtitle', sa.String(200), nullable=False,
                                      server_default='і ліжкового фонду стаціонару'))


def downgrade():
    with op.batch_alter_table('print_settings') as batch_op:
        batch_op.drop_column('form016_subtitle')
        batch_op.drop_column('form016_title')
        batch_op.drop_column('form007_subtitle')
        batch_op.drop_column('form007_title')
