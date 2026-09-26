"""Keep tables declared over a connection with the connection (D170).

Revision ID: c7d2e5a9f341
Revises: b6e20d84a971
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c7d2e5a9f341"
down_revision = "b6e20d84a971"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "connector",
        sa.Column(
            "declared_tables",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("connector", "declared_tables")
