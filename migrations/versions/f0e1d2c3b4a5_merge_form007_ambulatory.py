"""merge form007 + ambulatory heads

Об'єднує два паралельних alembic-heads, що утворилися після злиття main → statisty:
- d4e5f6a7b8c9 — гілка Форм 007/016 (print_settings dept title)
- 4d6e543ef206 — гілка амбулаторки (is_urgent)

Без операцій: лише зводить обидві лінії в один head.

Revision ID: f0e1d2c3b4a5
Revises: d4e5f6a7b8c9, 4d6e543ef206
Create Date: 2026-06-03

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f0e1d2c3b4a5'
down_revision = ('d4e5f6a7b8c9', '4d6e543ef206')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
