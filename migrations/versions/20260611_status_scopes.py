"""Add is_system to status_options + seed records/nszu scopes

Revision ID: 20260611_status_scopes
Revises: 20260611_add_status_options
Create Date: 2026-06-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260611_status_scopes'
down_revision = '20260611_add_status_options'
branch_labels = None
depends_on = None


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
    sa.column('is_system', sa.Boolean),
)


def upgrade():
    with op.batch_alter_table('status_options', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_system', sa.Boolean(), server_default='0', nullable=False))

    # records: усі три системні — на них тримаються статистика і tg-бот
    op.bulk_insert(status_options, [
        {'scope': 'records', 'name': 'Виписаний', 'color': 'success',
         'icon': 'bi-check-circle', 'sort_order': 10, 'is_default': False,
         'is_active': True, 'show_in_stats': True, 'is_system': True},
        {'scope': 'records', 'name': 'Опрацьовується', 'color': 'warning',
         'icon': 'bi-clock', 'sort_order': 20, 'is_default': True,
         'is_active': True, 'show_in_stats': True, 'is_system': True},
        {'scope': 'records', 'name': 'Порушені вимоги', 'color': 'danger',
         'icon': 'bi-exclamation-triangle', 'sort_order': 30, 'is_default': False,
         'is_active': True, 'show_in_stats': True, 'is_system': True},
        # легасі-статус: смерть ведеться через date_of_death; неактивний,
        # щоб старі записи рендерились і проходили валідацію
        {'scope': 'records', 'name': 'Помер', 'color': 'danger',
         'icon': 'bi-heartbreak', 'sort_order': 40, 'is_default': False,
         'is_active': False, 'show_in_stats': False, 'is_system': False},
        # nszu: 'В обробці' — системний (дефолт моделі NSZUCorrection);
        # кольори відтворюють історичні бейджі nszu_list
        {'scope': 'nszu', 'name': 'В обробці', 'color': 'secondary',
         'icon': 'bi-clock', 'sort_order': 10, 'is_default': True,
         'is_active': True, 'show_in_stats': True, 'is_system': True},
        {'scope': 'nszu', 'name': 'Опрацьовано', 'color': 'warning',
         'icon': 'bi-hourglass-split', 'sort_order': 20, 'is_default': False,
         'is_active': True, 'show_in_stats': True, 'is_system': False},
        {'scope': 'nszu', 'name': 'Оплачено', 'color': 'success',
         'icon': 'bi-check-circle', 'sort_order': 30, 'is_default': False,
         'is_active': True, 'show_in_stats': True, 'is_system': False},
        {'scope': 'nszu', 'name': 'Не підлягає оплаті', 'color': 'danger',
         'icon': 'bi-x-circle', 'sort_order': 40, 'is_default': False,
         'is_active': True, 'show_in_stats': True, 'is_system': False},
    ])


def downgrade():
    op.execute("DELETE FROM status_options WHERE scope IN ('records', 'nszu')")
    with op.batch_alter_table('status_options', schema=None) as batch_op:
        batch_op.drop_column('is_system')
