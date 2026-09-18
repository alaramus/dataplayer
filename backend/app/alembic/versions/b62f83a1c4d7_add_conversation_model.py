"""add conversation model

A conversation may be held with a model of its own; empty means the one chosen
in the settings (D140).

Revision ID: b62f83a1c4d7
Revises: a71c4d0e93b2
Create Date: 2026-09-18 11:04:19.552130

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'b62f83a1c4d7'
down_revision = 'a71c4d0e93b2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'conversation',
        sa.Column('model_key', sqlmodel.sql.sqltypes.AutoString(length=160), nullable=True),
    )


def downgrade():
    op.drop_column('conversation', 'model_key')
