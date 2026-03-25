"""Add adsj and suma columns to records

Revision ID: 20260321_add_adsj_suma
Revises: e451abd846fe
Create Date: 2026-03-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260321_add_adsj_suma'
down_revision = 'e451abd846fe'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('adsj', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('suma', sa.Numeric(precision=12, scale=2), nullable=True))


def downgrade():
    with op.batch_alter_table('records', schema=None) as batch_op:
        batch_op.drop_column('suma')
        batch_op.drop_column('adsj')
