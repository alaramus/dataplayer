"""add conversation change policy

What the agent may do to data in one conversation: read only, ask, or allow.
It replaces the conversation's `allow_all_changes`, which said only the last
two of the three (D136).

Revision ID: c93b17f5e2a8
Revises: b62f83a1c4d7
Create Date: 2026-09-18 12:26:07.884512

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'c93b17f5e2a8'
down_revision = 'b62f83a1c4d7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'conversation',
        sa.Column(
            'change_policy',
            sqlmodel.sql.sqltypes.AutoString(length=16),
            server_default='ask',
            nullable=False,
        ),
    )
    op.execute("UPDATE conversation SET change_policy = 'allow' WHERE allow_all_changes")
    op.drop_column('conversation', 'allow_all_changes')


def downgrade():
    op.add_column(
        'conversation',
        sa.Column('allow_all_changes', sa.Boolean(), server_default='false', nullable=False),
    )
    op.execute("UPDATE conversation SET allow_all_changes = true WHERE change_policy = 'allow'")
    op.drop_column('conversation', 'change_policy')
