"""the short tours a person has taken (D356)

Revision ID: d4f1a7c9e2b3
Revises: c3d8e1f5a2b7
Create Date: 2026-11-10 16:00:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d4f1a7c9e2b3"
down_revision = "c3d8e1f5a2b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "userpreferences",
        sa.Column(
            "tours_done",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("userpreferences", "tours_done")
