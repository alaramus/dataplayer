"""kept names for search (D212-D215)

Revision ID: 7c1e5a9d2b40
Revises: 4ed1ecd15a39
Create Date: 2026-10-11 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '7c1e5a9d2b40'
down_revision = '4ed1ecd15a39'
branch_labels = None
depends_on = None


def upgrade():
    # Trusted since PostgreSQL 13: the database's owner creates it. The index
    # below is built on an empty table, so it is not built CONCURRENTLY.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table('search_keep',
    sa.Column('connector_id', sa.Uuid(), nullable=False),
    sa.Column('window_seconds', sa.Integer(), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('stale_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('refresh_asked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('pass_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('pass_ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('outcome', sqlmodel.sql.sqltypes.AutoString(length=16), nullable=True),
    sa.Column('kept_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('kept_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('kept_notice', sa.Text(), nullable=True),
    sa.Column('names', sa.Integer(), nullable=False),
    sa.Column('notice', sa.Text(), nullable=True),
    sa.Column('error_kind', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True),
    sa.ForeignKeyConstraint(['connector_id'], ['connector.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('connector_id')
    )
    op.create_table('search_name',
    sa.Column('connector_id', sa.Uuid(), nullable=False),
    sa.Column('node_id', sa.Text(), nullable=False),
    sa.Column('parent_id', sa.Text(), nullable=True),
    sa.Column('scope', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('folded', sa.Text(), nullable=False),
    sa.Column('kind', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
    sa.Column('location', sa.Text(), nullable=False),
    sa.Column('node', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('ancestors', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('pass_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['connector_id'], ['connector.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('connector_id', 'node_id')
    )
    op.create_index('ix_search_name_folded', 'search_name', ['folded'], unique=False, postgresql_using='gin', postgresql_ops={'folded': 'gin_trgm_ops'})


def downgrade():
    op.drop_index('ix_search_name_folded', table_name='search_name', postgresql_using='gin', postgresql_ops={'folded': 'gin_trgm_ops'})
    op.drop_table('search_name')
    op.drop_table('search_keep')
