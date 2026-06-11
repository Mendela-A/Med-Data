"""Add status_options dictionary table + seed ambulatory statuses

Revision ID: 20260611_add_status_options
Revises: 4d6e543ef206
Create Date: 2026-06-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260611_add_status_options'
down_revision = '4d6e543ef206'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'status_options',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scope', sa.String(length=20), server_default='ambulatory', nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('color', sa.String(length=20), server_default='secondary', nullable=False),
        sa.Column('icon', sa.String(length=50), server_default='bi-circle', nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_default', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('show_in_stats', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scope', 'name', name='uq_status_options_scope_name'),
    )
    op.create_index('idx_status_options_scope', 'status_options', ['scope'])

    # Data seed: поточні захардкоджені статуси амбулаторії.
    # show_in_stats відтворює сьогоднішні stat-pills (піли мають лише
    # «Виписаний» та «Епізод відсутній»).
    status_options = sa.table(
        'status_options',
        sa.column('scope', sa.String),
        sa.column('name', sa.String),
        sa.column('color', sa.String),
        sa.column('icon', sa.String),
        sa.column('sort_order', sa.Integer),
        sa.column('is_default', sa.Boolean),
        sa.column('is_active', sa.Boolean),
        sa.column('show_in_stats', sa.Boolean),
    )
    op.bulk_insert(status_options, [
        {'scope': 'ambulatory', 'name': 'Виписаний', 'color': 'success',
         'icon': 'bi-check-circle', 'sort_order': 10, 'is_default': False,
         'is_active': True, 'show_in_stats': True},
        {'scope': 'ambulatory', 'name': 'Опрацьовується', 'color': 'warning',
         'icon': 'bi-clock', 'sort_order': 20, 'is_default': True,
         'is_active': True, 'show_in_stats': False},
        {'scope': 'ambulatory', 'name': 'Порушені вимоги', 'color': 'danger',
         'icon': 'bi-exclamation-triangle', 'sort_order': 30, 'is_default': False,
         'is_active': True, 'show_in_stats': False},
        {'scope': 'ambulatory', 'name': 'Епізод відсутній', 'color': 'dark',
         'icon': 'bi-file-earmark-x', 'sort_order': 40, 'is_default': False,
         'is_active': True, 'show_in_stats': True},
    ])


def downgrade():
    op.drop_index('idx_status_options_scope', table_name='status_options')
    op.drop_table('status_options')
