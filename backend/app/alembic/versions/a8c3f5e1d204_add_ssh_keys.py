"""add ssh keys

A person's SSH keys, apart from the connections that sign in with them. The
private half is encrypted under the connector key; an asked-for passphrase is
never written here (D146, D147).

Revision ID: a8c3f5e1d204
Revises: e5b21c7d90a3
Create Date: 2026-09-18 21:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8c3f5e1d204'
down_revision = 'e5b21c7d90a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sshkey',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('algorithm', sa.String(length=64), nullable=False),
        sa.Column('public_key', sa.Text(), nullable=False),
        sa.Column('fingerprint', sa.String(length=128), nullable=False),
        sa.Column('private_key', sa.LargeBinary(), nullable=False),
        sa.Column(
            'passphrase_mode', sa.String(length=8), server_default='none', nullable=False
        ),
        sa.Column('passphrase', sa.LargeBinary(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sshkey_owner', 'sshkey', ['owner_id'], unique=False)


def downgrade():
    op.drop_index('ix_sshkey_owner', table_name='sshkey')
    op.drop_table('sshkey')
