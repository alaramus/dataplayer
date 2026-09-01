"""add query document

Revision ID: d2f60b81c3a7
Revises: b71c4e9d2a08
Create Date: 2026-09-01 16:40:11.320544

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'd2f60b81c3a7'
down_revision = 'b71c4e9d2a08'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'querydocument',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        # Nulled rather than cascaded: a document survives losing its context,
        # and what it loses is the ability to run (D63).
        sa.Column('connector_id', sa.Uuid(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=True),
        # Ciphertext under QUERY_CONTENT_KEY. Nothing reads this column
        # without going through app.queries.content.
        sa.Column('body', sa.LargeBinary(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('search_path', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('layout', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trashed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['connector_id'], ['connector.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_querydocument_owner_id', 'querydocument', ['owner_id'], unique=False
    )
    op.create_index(
        'ix_querydocument_connector_id', 'querydocument', ['connector_id'], unique=False
    )
    # The sweep asks for expired rows and nothing else.
    op.create_index(
        'ix_querydocument_trashed_at', 'querydocument', ['trashed_at'], unique=False
    )
    # The library is read as "mine, newest first".
    op.create_index(
        'ix_querydocument_owner_updated',
        'querydocument',
        ['owner_id', 'updated_at'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_querydocument_owner_updated', table_name='querydocument')
    op.drop_index('ix_querydocument_trashed_at', table_name='querydocument')
    op.drop_index('ix_querydocument_connector_id', table_name='querydocument')
    op.drop_index('ix_querydocument_owner_id', table_name='querydocument')
    op.drop_table('querydocument')
