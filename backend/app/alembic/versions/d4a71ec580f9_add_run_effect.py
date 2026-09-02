"""add the effect of a run's structure changes

Revision ID: d4a71ec580f9
Revises: c9f24a7b6e30
Create Date: 2026-09-02 10:12:44.108231

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'd4a71ec580f9'
down_revision = 'c9f24a7b6e30'
branch_labels = None
depends_on = None


def upgrade():
    # What the source said has to be re-read after this run's structure
    # changes became permanent. Null for every run written before this column
    # existed, which is right: none of them could run a structure change (D66).
    op.add_column(
        'executionrun',
        sa.Column('effect', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade():
    op.drop_column('executionrun', 'effect')
