"""the card a service's connection was made from, for the types given cards (D377)

Revision ID: b8e3f2a6c9d4
Revises: a7c4e1b9d2f5
Create Date: 2026-11-17 16:00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b8e3f2a6c9d4"
down_revision = "a7c4e1b9d2f5"
branch_labels = None
depends_on = None

# PostgreSQL, Redis and Kafka had no cards when c3d8e1f5a2b7 ran, so a
# connection their services made was left as its type. A TimescaleDB service
# is the one this changes on screen.


def upgrade() -> None:
    op.execute(
        """
        UPDATE connector SET face = managedservice.template_key
        FROM managedservice
        WHERE managedservice.connector_id = connector.id
          AND connector.face IS NULL
          AND managedservice.template_key IN
              ('postgres', 'timescaledb', 'redis', 'kafka')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE connector SET face = NULL
        WHERE face IN ('postgres', 'timescaledb', 'redis', 'kafka')
        """
    )
