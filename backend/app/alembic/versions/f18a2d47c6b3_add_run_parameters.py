"""add run parameters and remembered values

Revision ID: f18a2d47c6b3
Revises: e7c31f5a90d4
Create Date: 2026-09-01 19:05:02.884411

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'f18a2d47c6b3'
down_revision = 'e7c31f5a90d4'
branch_labels = None
depends_on = None


def upgrade():
    # What a document was told to remember being asked with, encrypted like its
    # body. Never a value marked secret when it ran (D63).
    op.add_column(
        'querydocument', sa.Column('parameters', sa.LargeBinary(), nullable=True)
    )
    # Names and shape of the bindings one run was given — never their values.
    op.add_column(
        'executionrun',
        sa.Column(
            'parameters',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='[]',
        ),
    )
    # Whether Run meant one statement or a whole script.
    op.add_column(
        'executionrun',
        sa.Column(
            'scope', sa.String(length=16), nullable=False, server_default='statement'
        ),
    )


def downgrade():
    op.drop_column('executionrun', 'scope')
    op.drop_column('executionrun', 'parameters')
    op.drop_column('querydocument', 'parameters')
