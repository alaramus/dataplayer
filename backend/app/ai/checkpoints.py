"""The model's working state, in LangGraph's own PostgreSQL saver (D139).

Used as shipped, under three conditions stated here once: what it writes is
encrypted under the conversation key, what it reads back may only be the types
LangGraph lists as safe, and its tables are created by `app/prepare_checkpoints.py`
at prestart rather than by Alembic, which is told to leave them alone.

The connection pool is handed in by whoever assembles the application: it is
`psycopg`, which stays inside the postgres adapter.
"""

from langgraph.checkpoint.postgres._ainternal import Conn
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import crypto

# What `setup()` creates. Named for Alembic, which would otherwise read them as
# tables to drop (`app/alembic/env.py`).
CHECKPOINT_TABLES = frozenset(
    {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"}
)


def serializer() -> EncryptedSerializer:
    # By default LangGraph rebuilds any Python type it finds in a checkpoint,
    # which is code execution for whoever can write to the table. None is its
    # strict mode: the types it lists as safe, messages among them.
    strict = JsonPlusSerializer(allowed_msgpack_modules=None)
    return EncryptedSerializer.from_pycryptodome_aes(
        strict, key=crypto.key_of("ai_content")
    )


def checkpointer(pool: Conn) -> AsyncPostgresSaver:
    """The saver over a pool. `Conn` is LangGraph's own name for what it
    accepts, from a module it marks private, used only to say so."""
    return AsyncPostgresSaver(pool, serde=serializer())


_LATEST = text(
    "SELECT checkpoint_id FROM checkpoints"
    " WHERE thread_id = :thread AND checkpoint_ns = ''"
    " ORDER BY checkpoint_id DESC LIMIT 1"
)
# Everything but the latest state, the blobs its channel versions name and the
# writes pending on it — a pause's answer is one of those.
_DROP_OLDER = (
    text(
        "DELETE FROM checkpoint_writes"
        " WHERE thread_id = :thread AND checkpoint_ns = '' AND checkpoint_id <> :latest"
    ),
    text(
        "DELETE FROM checkpoint_blobs b"
        " WHERE b.thread_id = :thread AND b.checkpoint_ns = ''"
        " AND NOT EXISTS ("
        "   SELECT 1 FROM checkpoints c"
        "   CROSS JOIN LATERAL jsonb_each_text(c.checkpoint -> 'channel_versions')"
        "     AS v(channel, version)"
        "   WHERE c.thread_id = b.thread_id AND c.checkpoint_ns = ''"
        "   AND c.checkpoint_id = :latest"
        "   AND v.channel = b.channel AND v.version = b.version)"
    ),
    text(
        "DELETE FROM checkpoints"
        " WHERE thread_id = :thread AND checkpoint_ns = '' AND checkpoint_id <> :latest"
    ),
)


async def keep_latest(session: AsyncSession, thread_id: str) -> None:
    """Keep only the state a conversation continues from (D139).

    Written against LangGraph's tables because its saver declares `aprune` and
    does not implement it: 3.1.2 raises NotImplementedError. Every answer
    otherwise stores the whole conversation once more. The tests that a
    conversation holds one state and still continues are what notice when an
    upgrade changes these tables.
    """
    latest = (
        await session.exec(_LATEST.bindparams(thread=thread_id))  # type: ignore[call-overload]  # a statement over LangGraph's tables, which have no model here
    ).scalar_one_or_none()
    if latest is None:
        return
    for statement in _DROP_OLDER:
        await session.exec(statement.bindparams(thread=thread_id, latest=latest))  # type: ignore[call-overload]  # as above
    await session.commit()


async def prepare(pool: Conn) -> None:
    """Create or migrate LangGraph's tables.

    Never inside the application: its migrations build indexes CONCURRENTLY,
    which waits for every open transaction in the database, and a process
    that holds one while it waits waits for ever.
    """
    await checkpointer(pool).setup()
