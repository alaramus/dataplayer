"""add metrics agents and the metrics store setting

Revision ID: a7d3e9c1b524
Revises: b1f0c47d29ae
Create Date: 2026-09-13 12:00:00.000000

Agents a person registers, with the key they report under, and the one row
that says where the installation's metrics store is (D126, D128). A service
now says what it is for, so the store started as one stays out of every
person's list of services.

"""
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a7d3e9c1b524'
down_revision = 'b1f0c47d29ae'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'managedservice',
        sa.Column(
            'purpose',
            sqlmodel.sql.sqltypes.AutoString(length=16),
            nullable=False,
            server_default='connection',
        ),
    )
    op.alter_column('managedservice', 'purpose', server_default=None)
    op.create_index(
        op.f('ix_managedservice_purpose'), 'managedservice', ['purpose'], unique=False
    )

    op.create_table(
        'metricsagent',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column(
            'key_fingerprint', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False
        ),
        sa.Column('key_sealed', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('key_issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_metricsagent_owner_id'), 'metricsagent', ['owner_id'], unique=False
    )
    op.create_index(
        op.f('ix_metricsagent_key_fingerprint'),
        'metricsagent',
        ['key_fingerprint'],
        unique=True,
    )

    op.create_table(
        'metricsstoresetting',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('secrets', sa.LargeBinary(), nullable=False),
        sa.Column('service_id', sa.Uuid(), nullable=True),
        sa.Column('configured_by', sa.Uuid(), nullable=True),
        sa.Column('configured_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('id = 1', name='metrics_store_is_one_row'),
        sa.ForeignKeyConstraint(['service_id'], ['managedservice.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['configured_by'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('metricsstoresetting')
    op.drop_index(op.f('ix_metricsagent_key_fingerprint'), table_name='metricsagent')
    op.drop_index(op.f('ix_metricsagent_owner_id'), table_name='metricsagent')
    op.drop_table('metricsagent')
    op.drop_index(op.f('ix_managedservice_purpose'), table_name='managedservice')
    op.drop_column('managedservice', 'purpose')
