"""Move saved DeepSeek Flash selections to its current API model ID.

Revision ID: d3f4a9c17b62
Revises: c61e2b9a74f0
"""

from alembic import op


revision = "d3f4a9c17b62"
down_revision = "c61e2b9a74f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE agentpreferences SET model_key = 'deepseek:deepseek-flash' "
        "WHERE model_key = 'deepseek:deepseek-v4-flash'"
    )
    op.execute(
        "UPDATE conversation SET model_key = 'deepseek:deepseek-flash' "
        "WHERE model_key = 'deepseek:deepseek-v4-flash'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE agentpreferences SET model_key = 'deepseek:deepseek-v4-flash' "
        "WHERE model_key = 'deepseek:deepseek-flash'"
    )
    op.execute(
        "UPDATE conversation SET model_key = 'deepseek:deepseek-v4-flash' "
        "WHERE model_key = 'deepseek:deepseek-flash'"
    )
