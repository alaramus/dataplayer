"""add metrics reporting of connections

Revision ID: d2e6a9f4c718
Revises: c4b8f2d6e913
Create Date: 2026-09-13 18:00:00.000000

Whether a connection reports its own metrics to dashboards, and how often
(D128). A row of its own, gone with the connection.

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd2e6a9f4c718'
down_revision = 'c4b8f2d6e913'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'metricsconnector',
        sa.Column('connector_id', sa.Uuid(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('interval_seconds', sa.Integer(), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['connector_id'], ['connector.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('connector_id'),
    )


def downgrade():
    op.drop_table('metricsconnector')
