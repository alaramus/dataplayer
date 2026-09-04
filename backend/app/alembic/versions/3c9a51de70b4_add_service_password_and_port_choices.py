"""add service password and port choices

Revision ID: 3c9a51de70b4
Revises: 1200df757fc0
Create Date: 2026-09-03 12:40:11.204118

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3c9a51de70b4'
down_revision = '1200df757fc0'
branch_labels = None
depends_on = None


def upgrade():
    # Null means the runtime picks, which is what every service made before
    # this migration was started with.
    op.add_column(
        'managedservice', sa.Column('requested_port', sa.Integer(), nullable=True)
    )
    # Everything started until now had its password made up here, so that is
    # what the server default says. It stays on the column because the model
    # has the same default.
    op.add_column(
        'managedservice',
        sa.Column(
            'password_mode',
            sa.String(length=16),
            nullable=False,
            server_default='generated',
        ),
    )
    # A password somebody typed, encrypted, and only until the connector holds
    # it. Nothing written before this migration has one.
    op.add_column(
        'managedservice', sa.Column('chosen_password', sa.LargeBinary(), nullable=True)
    )
    op.add_column(
        'managedservice', sa.Column('connected_at', sa.DateTime(timezone=True), nullable=True)
    )
    # Every service that already has a connection became one at some point,
    # and the row has to say so: without this a running database would be
    # offered a retry the moment its connection was deleted, and retry starts
    # over by destroying what the earlier attempt left (D84). The creation
    # time is the closest fact this table holds; it is only ever compared
    # against null.
    op.execute(
        'UPDATE managedservice SET connected_at = created_at '
        'WHERE connector_id IS NOT NULL'
    )
    # The password is not shown at all any more, so the stamp that rationed it
    # has nothing left to say (D89).
    op.drop_column('managedservice', 'credentials_shown_at')


def downgrade():
    op.add_column(
        'managedservice',
        sa.Column('credentials_shown_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_column('managedservice', 'connected_at')
    op.drop_column('managedservice', 'chosen_password')
    op.drop_column('managedservice', 'password_mode')
    op.drop_column('managedservice', 'requested_port')
