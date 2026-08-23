"""add auth_method to postgres connectors

Revision ID: a7f1c2d43b90
Revises: 5f2f8ce7805a
Create Date: 2026-08-23 11:20:00.000000

PostgreSQL options become a discriminated union, and Pydantic refuses an
object that names no variant. Every connector saved before this therefore
stops being readable — and one that cannot be read cannot be opened, checked
or browsed. Nothing fails at startup; it fails at the first request.

Data only: the column is jsonb and its shape does not change. `user_password`
rather than `no_auth` because every existing connector has a password — it
could not have been saved without one.

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a7f1c2d43b90'
down_revision = '5f2f8ce7805a'
branch_labels = None
depends_on = None

# Named so that the test can run the very statement the migration runs. Only
# rows that name no method are touched: filling in what is missing must not
# overwrite what is already there.
FILL_AUTH_METHOD = """
UPDATE connector
SET config = jsonb_set(config, '{auth_method}', '"user_password"')
WHERE adapter_type = 'postgres' AND NOT (config ? 'auth_method')
"""

DROP_AUTH_METHOD = """
UPDATE connector
SET config = config - 'auth_method'
WHERE adapter_type = 'postgres'
"""


def upgrade():
    op.execute(FILL_AUTH_METHOD)


def downgrade():
    op.execute(DROP_AUTH_METHOD)
