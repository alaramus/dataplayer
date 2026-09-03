"""add service start choices

Revision ID: 1200df757fc0
Revises: ff478728ab92
Create Date: 2026-09-03 06:13:15.920455

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1200df757fc0'
down_revision = 'ff478728ab92'
branch_labels = None
depends_on = None


def upgrade():
    # Server defaults so that services started before this migration keep
    # working: they were made without a port on the host and without sample
    # data, which is exactly what these say. The default stays on the column
    # rather than being dropped afterwards, because the model has one too and
    # a row written by anything else should agree with it.
    op.add_column(
        'managedservice',
        sa.Column('publish', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'managedservice',
        sa.Column(
            'sample_data', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        'managedservice',
        sa.Column(
            'chosen_credentials',
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    # Nullable, and null means "not yet": a service made before this migration
    # has had its password shown to nobody, and asking for it is still allowed.
    op.add_column(
        'managedservice',
        sa.Column('credentials_shown_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column('managedservice', 'credentials_shown_at')
    op.drop_column('managedservice', 'chosen_credentials')
    op.drop_column('managedservice', 'sample_data')
    op.drop_column('managedservice', 'publish')
