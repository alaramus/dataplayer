"""add grants on dashboards

Revision ID: e5a1c7d3b940
Revises: d2e6a9f4c718
Create Date: 2026-09-13 21:00:00.000000

Somebody else's standing on a dashboard: read or write (D129). Gone with the
dashboard and with the person.

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e5a1c7d3b940'
down_revision = 'd2e6a9f4c718'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dashboardgrant',
        sa.Column('dashboard_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('access', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['dashboard_id'], ['dashboard.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('dashboard_id', 'user_id'),
    )
    op.create_index('ix_dashboardgrant_user_id', 'dashboardgrant', ['user_id'], unique=False)


def downgrade():
    op.drop_index('ix_dashboardgrant_user_id', table_name='dashboardgrant')
    op.drop_table('dashboardgrant')
