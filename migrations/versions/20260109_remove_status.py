"""Remove status column from records

Revision ID: 20260109_remove_status
Revises: 
Create Date: 2026-01-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260109_remove_status'
down_revision = None
branch_labels = None
depend_on = None


def upgrade():
    # Drop the 'status' column from records table
    with op.get_context().autocommit_block():
        try:
            op.drop_column('records', 'status')
        except Exception:
            # Column might not exist; log or ignore
            print('Warning: could not drop column records.status (may not exist)')


def downgrade():
    # Re-create the status column if downgrading
    op.add_column('records', sa.Column('status', sa.String(length=200), nullable=True))
