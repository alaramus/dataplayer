"""drop connector name unique constraint

Revision ID: b8c4d2e91a57
Revises: a7f1c2d43b90
Create Date: 2026-08-24

Connector names are no longer required to be unique per owner;
only the connector id is unique.

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b8c4d2e91a57"
down_revision = "a7f1c2d43b90"
branch_labels = None
depends_on = None


def upgrade():
    # Use raw SQL with IF EXISTS so the migration is idempotent when
    # the database has already been created without the constraint.
    op.execute(sa.text("ALTER TABLE connector DROP CONSTRAINT IF EXISTS uq_connector_owner_name"))


def downgrade():
    op.create_unique_constraint(
        "uq_connector_owner_name", "connector", ["owner_id", "name"]
    )
