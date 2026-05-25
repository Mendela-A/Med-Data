"""add_print_settings

Revision ID: a1b2c3d4e5f6
Revises: 8e7992f1ab9a
Create Date: 2026-05-25

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '8e7992f1ab9a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'print_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ministry', sa.String(length=200), nullable=False),
        sa.Column('org_name', sa.String(length=200), nullable=False),
        sa.Column('org_short_name', sa.String(length=100), nullable=False),
        sa.Column('org_address', sa.String(length=300), nullable=False),
        sa.Column('signer1_title', sa.String(length=200), nullable=False),
        sa.Column('signer1_name', sa.String(length=100), nullable=False),
        sa.Column('signer2_label', sa.String(length=100), nullable=False),
        sa.Column('signer2_name', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute(
        """INSERT INTO print_settings (id, ministry, org_name, org_short_name, org_address,
               signer1_title, signer1_name, signer2_label, signer2_name)
           VALUES (1,
               'Міністерство охорони здоров''я України',
               'КНП «Калуська центральна районна лікарня»',
               'КНП «Калуська ЦРЛ»',
               'вул. Каракая, 25, м. Калуш, Івано-Франківська обл., 77300',
               'Заступник генерального директора',
               'Л. Луців',
               'Відповідальний:',
               'Валерій ПАЛЯНИЦЯ')"""
    )


def downgrade():
    op.drop_table('print_settings')
