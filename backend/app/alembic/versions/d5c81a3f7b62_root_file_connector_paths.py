"""store file connector paths rooted

Revision ID: d5c81a3f7b62
Revises: c7a4e1b93d20
Create Date: 2026-09-07 10:00:00.000000

A file connection now stores the folder it points at the way a path is
written: "/" for the root of personal storage, "/reports" for a folder in it.
Rows written before this hold the same folder without its leading separator,
and the root as the empty string — which reads like an option nobody filled
in.

Data only: the column is jsonb and its shape does not change. Nothing breaks
without this migration — the driver joins from the value either way — so it
exists to keep one form in the table rather than two.

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd5c81a3f7b62'
down_revision = 'c7a4e1b93d20'
branch_labels = None
depends_on = None

# Named so that the test can run the very statement the migration runs. Only
# rows not already rooted are touched, so running it twice changes nothing.
# `left(...)` rather than `LIKE '/%'`: psycopg reads a literal % as a
# placeholder as soon as anything supplies parameters, and a migration is not
# the place to depend on nothing ever doing so.
ROOT_FILE_PATHS = """
UPDATE connector
SET config = jsonb_set(config, '{path}', to_jsonb('/' || ltrim(config->>'path', '/')))
WHERE adapter_type = 'file' AND config ? 'path' AND left(config->>'path', 1) <> '/'
"""

UNROOT_FILE_PATHS = """
UPDATE connector
SET config = jsonb_set(config, '{path}', to_jsonb(ltrim(config->>'path', '/')))
WHERE adapter_type = 'file' AND left(config->>'path', 1) = '/'
"""


def upgrade():
    op.execute(ROOT_FILE_PATHS)


def downgrade():
    op.execute(UNROOT_FILE_PATHS)
