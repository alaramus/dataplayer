"""add user preferences

Revision ID: b1f0c47d29ae
Revises: d5c81a3f7b62
Create Date: 2026-09-12 10:00:00.000000

One row per user, written the first time they choose anything. Everybody who
never opened the screen has no row, and the defaults in
`app/users/preferences.py` are the answer for them.

"""
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b1f0c47d29ae'
down_revision = 'd5c81a3f7b62'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'userpreferences',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column(
            'connector_checks',
            sqlmodel.sql.sqltypes.AutoString(length=8),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade():
    op.drop_table('userpreferences')
