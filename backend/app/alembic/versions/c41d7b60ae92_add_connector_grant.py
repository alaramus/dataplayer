"""add connector grant

Revision ID: c41d7b60ae92
Revises: a35118a5a2e4
Create Date: 2026-08-29 21:40:12.114903

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c41d7b60ae92'
down_revision = 'a35118a5a2e4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'connectorgrant',
        sa.Column('connector_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('access', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['connector_id'], ['connector.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('connector_id', 'user_id'),
    )
    # Every list a user opens asks which connections are granted to them, and
    # the primary key leads with the connector.
    op.create_index(
        'ix_connectorgrant_user_id', 'connectorgrant', ['user_id'], unique=False
    )


def downgrade():
    op.drop_index('ix_connectorgrant_user_id', table_name='connectorgrant')
    op.drop_table('connectorgrant')
