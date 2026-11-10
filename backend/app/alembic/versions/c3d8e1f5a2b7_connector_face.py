"""the card a connection was made from (D264)

Revision ID: c3d8e1f5a2b7
Revises: b7c2e19a4d10
Create Date: 2026-11-10 10:30:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c3d8e1f5a2b7"
down_revision = "b7c2e19a4d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("connector", sa.Column("face", sa.String(length=32), nullable=True))
    # A connection a service made says which product it started; one typed by
    # hand predates the column and keeps its type's picture.
    op.execute(
        """
        UPDATE connector SET face = managedservice.template_key
        FROM managedservice
        WHERE managedservice.connector_id = connector.id
          AND managedservice.template_key IN ('mariadb', 'scylladb')
        """
    )


def downgrade() -> None:
    op.drop_column("connector", "face")
