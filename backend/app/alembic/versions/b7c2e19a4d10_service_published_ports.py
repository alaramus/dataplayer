"""a service's extra published ports (D333)

Revision ID: b7c2e19a4d10
Revises: 4ed1ecd15a39
Create Date: 2026-11-09 17:00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7c2e19a4d10"
down_revision = "4ed1ecd15a39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every row there is has none: only a template with extra ports fills it.
    op.add_column(
        "managedservice",
        sa.Column(
            "published_ports", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
    )


def downgrade() -> None:
    op.drop_column("managedservice", "published_ports")
