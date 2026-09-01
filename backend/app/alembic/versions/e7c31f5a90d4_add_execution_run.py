"""add execution run

Revision ID: e7c31f5a90d4
Revises: d2f60b81c3a7
Create Date: 2026-09-01 18:20:44.117903

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'e7c31f5a90d4'
down_revision = 'd2f60b81c3a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'executionrun',
        # The client's own UUID: starting a run is an idempotent command, so
        # the id is part of the command rather than issued by the server (D64).
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('connector_id', sa.Uuid(), nullable=True),
        sa.Column('document_id', sa.Uuid(), nullable=True),
        sa.Column('document_revision', sa.Integer(), nullable=True),
        # Ciphertext under QUERY_CONTENT_KEY, like a document's body (D63).
        sa.Column('text', sa.LargeBinary(), nullable=False),
        sa.Column('range_start', sa.Integer(), nullable=True),
        sa.Column('range_end', sa.Integer(), nullable=True),
        sa.Column('search_path', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('statement_count', sa.Integer(), nullable=False),
        sa.Column('error', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['connector_id'], ['connector.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['document_id'], ['querydocument.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_executionrun_owner_id', 'executionrun', ['owner_id'], unique=False)
    op.create_index(
        'ix_executionrun_connector_id', 'executionrun', ['connector_id'], unique=False
    )
    op.create_index(
        'ix_executionrun_document_id', 'executionrun', ['document_id'], unique=False
    )
    # The startup sweep asks for whatever was left non-terminal.
    op.create_index('ix_executionrun_status', 'executionrun', ['status'], unique=False)
    # History is read as "mine, newest first".
    op.create_index(
        'ix_executionrun_owner_created',
        'executionrun',
        ['owner_id', 'created_at'],
        unique=False,
    )

    op.create_table(
        'statementrun',
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('command_tag', sa.String(length=255), nullable=True),
        sa.Column('row_count', sa.Integer(), nullable=True),
        # Into the process-local store, and only while it is still there.
        sa.Column('result_id', sa.String(length=64), nullable=True),
        sa.Column('truncated', sa.Boolean(), nullable=False),
        sa.Column('diagnostic', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('notices', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['executionrun.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('run_id', 'ordinal'),
    )


def downgrade():
    op.drop_table('statementrun')
    op.drop_index('ix_executionrun_owner_created', table_name='executionrun')
    op.drop_index('ix_executionrun_status', table_name='executionrun')
    op.drop_index('ix_executionrun_document_id', table_name='executionrun')
    op.drop_index('ix_executionrun_connector_id', table_name='executionrun')
    op.drop_index('ix_executionrun_owner_id', table_name='executionrun')
    op.drop_table('executionrun')
