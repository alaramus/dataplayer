"""LangGraph's saver used as shipped, under D139's conditions."""

import uuid
from dataclasses import dataclass

from httpx import AsyncClient
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import text as sql
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.checkpoints import CHECKPOINT_TABLES, serializer
from tests.ai.conftest import (
    Script,
    Turn,
    new_conversation,
    ready_agent,
    send,
    settled,
    text,
)
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email


async def test_nothing_said_reaches_langgraphs_tables_in_the_clear(
    client: AsyncClient, script: Script, db: AsyncSession
) -> None:
    """Plain values of state are stored outside the serializer, so every column
    of every row is read, and the rows are counted first: an empty table would
    pass this without proving anything."""
    headers = await authentication_token_from_email(client=client, email=random_email(), db=db)
    await ready_agent(client, headers)
    marker = f"plaintext-{uuid.uuid4()}"
    script.turns += [Turn(pieces=[text(f"you said {marker}")]), Turn(pieces=[text("T")])]
    conversation_id = await new_conversation(client, headers)
    run = await send(client, headers, conversation_id, f"remember {marker}")
    await settled(client, headers, run["id"])

    # The state as JSON, and the blobs and writes as the bytes they are: a
    # bytea read as JSON is hex, where no marker would ever be found.
    counts = {
        "rows": "SELECT (SELECT count(*) FROM checkpoints WHERE thread_id = :thread)"
        " + (SELECT count(*) FROM checkpoint_blobs WHERE thread_id = :thread)",
        "in state": "SELECT count(*) FROM checkpoints"
        " WHERE thread_id = :thread AND (checkpoint::text || metadata::text) LIKE '%' || :marker || '%'",
        "in blobs": "SELECT count(*) FROM checkpoint_blobs"
        " WHERE thread_id = :thread AND position(convert_to(:marker, 'UTF8') IN blob) > 0",
        "in writes": "SELECT count(*) FROM checkpoint_writes"
        " WHERE thread_id = :thread AND position(convert_to(:marker, 'UTF8') IN blob) > 0",
    }
    found = {
        name: (
            await db.exec(  # type: ignore[call-overload]  # LangGraph's tables have no model here
                sql(statement).bindparams(
                    thread=conversation_id,
                    **({"marker": marker} if ":marker" in statement else {}),
                )
            )
        ).scalar_one()
        for name, statement in counts.items()
    }

    assert found["rows"] >= 2
    assert (found["in state"], found["in blobs"], found["in writes"]) == (0, 0, 0)


@dataclass
class Smuggled:
    """A type nobody allowed into a checkpoint, of a kind msgpack can carry."""

    payload: str = "run me"


def test_deserialization_rebuilds_only_the_types_langgraph_lists_as_safe() -> None:
    serde = serializer()

    message = serde.loads_typed(serde.dumps_typed(AIMessage(content="kept")))
    smuggled = serde.loads_typed(serde.dumps_typed(Smuggled()))

    assert isinstance(message, AIMessage)
    assert not isinstance(smuggled, Smuggled)


def test_what_is_written_cannot_be_read_without_the_key() -> None:
    kind, payload = serializer().dumps_typed(HumanMessage(content="secret words"))

    assert b"secret words" not in payload
    assert kind.endswith("+aes")


async def test_alembic_is_told_every_table_langgraph_made(db: AsyncSession) -> None:
    """A table missing from the list is one the next revision would drop."""
    tables = set(
        (
            await db.exec(  # type: ignore[call-overload]  # a catalog query
                sql(
                    "SELECT table_name FROM information_schema.tables"
                    " WHERE table_schema = 'public' AND table_name LIKE 'checkpoint%'"
                )
            )
        ).scalars().all()
    )

    assert tables == CHECKPOINT_TABLES

