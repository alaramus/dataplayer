"""add write state to a run

Revision ID: c9f24a7b6e30
Revises: b8e15d3f2a4c
Create Date: 2026-09-01 23:12:07.554120

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9f24a7b6e30'
down_revision = 'b8e15d3f2a4c'
branch_labels = None
depends_on = None


def upgrade():
    # What became of what a run changed. Every run written before this column
    # existed was a read, which is what the default says (D66).
    op.add_column(
        'executionrun',
        sa.Column(
            'write_state', sa.String(length=16), nullable=False, server_default='none'
        ),
    )
    # The transaction it went through, so ending one can settle every run of it.
    op.add_column(
        'executionrun', sa.Column('transaction_id', sa.String(length=64), nullable=True)
    )
    op.create_index(
        'ix_executionrun_transaction_id',
        'executionrun',
        ['transaction_id'],
        unique=False,
    )
    # What a change touched, which is not the same as how many rows came back
    # to be looked at (D66).
    op.add_column(
        'statementrun', sa.Column('affected_rows', sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column('statementrun', 'affected_rows')
    op.drop_index('ix_executionrun_transaction_id', table_name='executionrun')
    op.drop_column('executionrun', 'transaction_id')
    op.drop_column('executionrun', 'write_state')
