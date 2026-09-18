"""add message attachments

A file the person sent with a message: its name and bytes sealed like the
text, deleted with the message it came with (D142).

Revision ID: e5b21c7d90a3
Revises: d47ae09b31f6
Create Date: 2026-09-18 16:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'e5b21c7d90a3'
down_revision = 'd47ae09b31f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'messageattachment',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('message_id', sa.Uuid(), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('kind', sqlmodel.sql.sqltypes.AutoString(length=8), nullable=False),
        sa.Column('media_type', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('name', sa.LargeBinary(), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['conversationmessage.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_messageattachment_message_id'), 'messageattachment', ['message_id'], unique=False
    )


def downgrade():
    op.drop_index(op.f('ix_messageattachment_message_id'), table_name='messageattachment')
    op.drop_table('messageattachment')
