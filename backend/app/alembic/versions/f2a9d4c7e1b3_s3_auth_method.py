"""an S3 connection names how it signs in: its key, or an AWS account (D453)

Revision ID: f2a9d4c7e1b3
Revises: e4b7c2a9f1d3
Create Date: 2026-11-27 18:00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f2a9d4c7e1b3"
down_revision = "e4b7c2a9f1d3"
branch_labels = None
depends_on = None

# Every S3 connection made before signed in with an access key, the one way
# there was; the options became a union on `auth_method`.
UPGRADE = """
UPDATE connector
SET config = config || '{"auth_method": "access_key"}'::jsonb
WHERE adapter_type = 's3'
  AND NOT config ? 'auth_method'
"""

# Back to the one way. A connection that signs in with an account cannot be
# said without it and is left as it is: older code refuses to open it.
DOWNGRADE = """
UPDATE connector
SET config = config - 'auth_method'
WHERE adapter_type = 's3'
  AND config->>'auth_method' = 'access_key'
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
