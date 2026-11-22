"""a connection's TLS switch becomes the TLS block's mode and trust (D446)

Revision ID: d7e2f9a4c1b8
Revises: b8e3f2a6c9d4
Create Date: 2026-11-22 20:00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "d7e2f9a4c1b8"
down_revision = "b8e3f2a6c9d4"
branch_labels = None
depends_on = None

# `tls` (MongoDB, ZooKeeper, Kafka, RabbitMQ) or `secure` (ClickHouse,
# Cassandra) on meant "encrypted, verified": the name too everywhere but
# ZooKeeper, whose client never checked it. A CA certificate Kafka or RabbitMQ
# kept becomes the trusted authority. PostgreSQL and MySQL had no switch, and
# the block's default is what they did.
UPGRADE = """
UPDATE connector
SET config = (config - 'tls' - 'secure' - 'ca_certificate')
    || jsonb_build_object(
        'tls_mode',
        CASE
            WHEN COALESCE(config->>'tls', config->>'secure', 'false') = 'true'
                THEN CASE WHEN adapter_type = 'zookeeper' THEN 'verify_ca' ELSE 'verify_full' END
            ELSE 'disabled'
        END
    )
    || CASE
        WHEN COALESCE(config->>'ca_certificate', '') <> ''
            THEN jsonb_build_object(
                'tls_trust', 'certificate',
                'tls_ca_certificate', config->'ca_certificate'
            )
        ELSE '{}'::jsonb
    END
WHERE adapter_type IN ('mongodb', 'clickhouse', 'cassandra', 'zookeeper', 'kafka', 'rabbitmq')
  AND NOT config ? 'tls_mode'
"""

# Back to the switch, losing what it cannot say: a client certificate, and the
# difference between the verifying modes.
DOWNGRADE = """
UPDATE connector
SET config = (
        config - 'tls_mode' - 'tls_trust' - 'tls_ca_certificate' - 'tls_client_certificate'
    )
    || jsonb_build_object(
        CASE WHEN adapter_type IN ('clickhouse', 'cassandra') THEN 'secure' ELSE 'tls' END,
        COALESCE(config->>'tls_mode', 'disabled') <> 'disabled'
    )
    || CASE
        WHEN adapter_type IN ('kafka', 'rabbitmq')
            THEN jsonb_build_object(
                'ca_certificate',
                CASE WHEN config->>'tls_trust' = 'certificate'
                    THEN COALESCE(config->'tls_ca_certificate', '""'::jsonb)
                    ELSE '""'::jsonb
                END
            )
        ELSE '{}'::jsonb
    END
WHERE adapter_type IN ('mongodb', 'clickhouse', 'cassandra', 'zookeeper', 'kafka', 'rabbitmq')
  AND config ? 'tls_mode'
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
