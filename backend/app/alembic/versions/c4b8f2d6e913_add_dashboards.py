"""add dashboards

Revision ID: c4b8f2d6e913
Revises: a7d3e9c1b524
Create Date: 2026-09-13 15:00:00.000000

One row per dashboard of a person: a name, the layout of widgets as one JSON
body read and written whole, and a version raised by every save (D129).

"""
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c4b8f2d6e913'
down_revision = 'a7d3e9c1b524'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dashboard',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dashboard_owner_id'), 'dashboard', ['owner_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_dashboard_owner_id'), table_name='dashboard')
    op.drop_table('dashboard')
