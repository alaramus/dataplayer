"""add execution policy and write unlock

Revision ID: b8e15d3f2a4c
Revises: a4b9e0c7d215
Create Date: 2026-09-01 22:47:38.201995

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8e15d3f2a4c'
down_revision = 'a4b9e0c7d215'
branch_labels = None
depends_on = None


def upgrade():
    # What the owner allows SQL to do through this connection, above every
    # grant. Confirmation is the default, so a connection that existed before
    # this column asks rather than allows (D66).
    op.add_column(
        'connector',
        sa.Column(
            'execution_policy',
            sa.String(length=16),
            nullable=False,
            server_default='confirm_writes',
        ),
    )
    # That somebody deliberately left read-only, per person and per connection.
    # It expires by disuse, which is why the last use is kept.
    op.create_table(
        'writeunlock',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('connector_id', sa.Uuid(), nullable=False),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['connector_id'], ['connector.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'connector_id'),
    )


def downgrade():
    op.drop_table('writeunlock')
    op.drop_column('connector', 'execution_policy')
