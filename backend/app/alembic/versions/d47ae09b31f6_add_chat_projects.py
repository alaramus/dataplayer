"""add chat projects

A folder of conversations, and nothing more: deleting one leaves every
conversation it held, out of any folder (D141).

Revision ID: d47ae09b31f6
Revises: c93b17f5e2a8
Create Date: 2026-09-18 13:41:55.207318

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd47ae09b31f6'
down_revision = 'c93b17f5e2a8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'chatproject',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_chatproject_owner', 'chatproject', ['owner_id'], unique=False)
    op.add_column('conversation', sa.Column('project_id', sa.Uuid(), nullable=True))
    op.create_index(
        op.f('ix_conversation_project_id'), 'conversation', ['project_id'], unique=False
    )
    op.create_foreign_key(
        'conversation_project_id_fkey',
        'conversation',
        'chatproject',
        ['project_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade():
    op.drop_constraint('conversation_project_id_fkey', 'conversation', type_='foreignkey')
    op.drop_index(op.f('ix_conversation_project_id'), table_name='conversation')
    op.drop_column('conversation', 'project_id')
    op.drop_index('ix_chatproject_owner', table_name='chatproject')
    op.drop_table('chatproject')
