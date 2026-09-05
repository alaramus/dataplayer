"""add declared reference

Revision ID: c7a4e1b93d20
Revises: b3d75f21c8ea
Create Date: 2026-09-05 12:10:31.884210

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7a4e1b93d20'
down_revision = 'b3d75f21c8ea'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'declaredreference',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('author_id', sa.Uuid(), nullable=False),
        sa.Column('a_connector_id', sa.Uuid(), nullable=False),
        sa.Column('a_node_id', sa.String(length=1024), nullable=False),
        sa.Column('a_column', sa.String(length=255), nullable=False),
        sa.Column('a_label', sa.String(length=255), nullable=False),
        sa.Column('b_connector_id', sa.Uuid(), nullable=False),
        sa.Column('b_node_id', sa.String(length=1024), nullable=False),
        sa.Column('b_column', sa.String(length=255), nullable=False),
        sa.Column('b_label', sa.String(length=255), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['user.id'], ondelete='CASCADE'),
        # A reference to a connection that has been deleted is not a reference
        # to anything, so it goes with it rather than pointing at an id.
        sa.ForeignKeyConstraint(
            ['a_connector_id'], ['connector.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['b_connector_id'], ['connector.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        # The same pair drawn twice is the same reference (D106). Held here and
        # not only by the lookup before the insert, because two windows of one
        # person can press the button at the same moment.
        sa.UniqueConstraint(
            'author_id', 'fingerprint', name='uq_declaredreference_author_pair'
        ),
    )
    op.create_index(
        'ix_declaredreference_author_id', 'declaredreference', ['author_id']
    )
    # Every page of either node asks which references touch it, from both ends.
    op.create_index(
        'ix_declaredreference_a',
        'declaredreference',
        ['author_id', 'a_connector_id', 'a_node_id'],
    )
    op.create_index(
        'ix_declaredreference_b',
        'declaredreference',
        ['author_id', 'b_connector_id', 'b_node_id'],
    )


def downgrade():
    op.drop_index('ix_declaredreference_b', table_name='declaredreference')
    op.drop_index('ix_declaredreference_a', table_name='declaredreference')
    op.drop_index('ix_declaredreference_author_id', table_name='declaredreference')
    op.drop_table('declaredreference')
