"""add query retention

Revision ID: a4b9e0c7d215
Revises: f18a2d47c6b3
Create Date: 2026-09-01 19:31:56.740119

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4b9e0c7d215'
down_revision = 'f18a2d47c6b3'
branch_labels = None
depends_on = None


def upgrade():
    # One row per person who has chosen; everybody else has the default, so
    # there is nothing to write for a user who never opens the setting (D63).
    op.create_table(
        'queryretention',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('days', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade():
    op.drop_table('queryretention')
