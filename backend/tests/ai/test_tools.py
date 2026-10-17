import json
import uuid
from unittest.mock import MagicMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.tools import (
    MAX_RESULT_BYTES,
    MAX_TOOL_CALLS,
    ToolLimitReached,
    ToolRuntime,
    bounded_json,
    connector_ids_from_result,
    for_person,
    statement_substep,
    transfer_refusal,
)
from app.connectors.models import Connector
from app.core.config import settings
from app.core.translation import current_language, say
from app.users import crud as user_crud
from app.users.models import User


def test_tool_results_are_bounded_with_an_explicit_size() -> None:
    result = json.loads(bounded_json({"value": "x" * (MAX_RESULT_BYTES * 2)}))

    assert result["truncated"] is True
    assert result["serialized_bytes"] > MAX_RESULT_BYTES
    assert result["limit_bytes"] == MAX_RESULT_BYTES
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= MAX_RESULT_BYTES


def test_transfer_refusal_tells_owner_and_grantee_differently() -> None:
    connector = Connector(
        id=uuid.uuid4(),
        name="Accounts",
        adapter_type="postgres",
        config={},
        secrets=b"",
        owner_id=uuid.uuid4(),
    )

    owner = transfer_refusal(connector, "own")
    grantee = transfer_refusal(connector, "read")

    assert owner["error"] == "transfer_not_allowed"
    assert "Allow" in owner["message"]
    assert "owner" in grantee["message"]


def test_a_connector_result_can_be_identified_before_reuse() -> None:
    connector_id = uuid.uuid4()

    other = uuid.uuid4()

    assert connector_ids_from_result(json.dumps({"connector_id": str(connector_id)})) == {connector_id}
    assert connector_ids_from_result(
        json.dumps({"connector_ids": [str(connector_id), str(other)], "hits": []})
    ) == {connector_id, other}
    assert connector_ids_from_result(json.dumps({"connections": []})) == set()
    assert connector_ids_from_result("not json") == set()


def test_a_refusal_names_a_connection_but_is_never_withheld() -> None:
    connector = Connector(
        id=uuid.uuid4(),
        name="Accounts",
        adapter_type="postgres",
        config={},
        secrets=b"",
        owner_id=uuid.uuid4(),
    )

    refusal = transfer_refusal(connector, "read")

    assert refusal["connector_id"] == str(connector.id)
    assert connector_ids_from_result(json.dumps(refusal)) == set()


async def test_the_fifty_first_tool_call_is_refused_before_work_starts() -> None:
    async def ignored(*_args: object) -> None:
        return None

    runtime = ToolRuntime(
        run_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        resources=MagicMock(),
        data_cache=MagicMock(),
        say=ignored,
        opened=ignored,
        calls=MAX_TOOL_CALLS,
    )

    with pytest.raises(ToolLimitReached, match="50 tool calls"):
        await runtime.invoke("Too late", MagicMock())


async def test_a_tool_works_in_english_and_words_for_the_person_in_theirs(
    db: AsyncSession,
) -> None:
    """What a tool returns is read by the model, so it is English; what it
    shows the person is in the language they asked in (D226)."""
    owner = await user_crud.get_user_by_email(session=db, email=settings.FIRST_SUPERUSER)
    assert owner is not None

    async def ignored(*_args: object) -> None:
        return None

    async def work(_session: AsyncSession, _user: User) -> dict[str, str]:
        return {
            "model": say("Allow"),
            "person": for_person(lambda: say("Allow")),
            "substep": for_person(
                lambda: statement_substep({"ordinal": 0, "status": "succeeded", "row_count": 3})
            ),
        }

    runtime = ToolRuntime(
        run_id=uuid.uuid4(),
        owner_id=owner.id,
        conversation_id=uuid.uuid4(),
        resources=MagicMock(),
        data_cache=MagicMock(),
        say=ignored,
        opened=ignored,
        # A resumed step is not announced, so no run row is needed.
        resume_ordinal=1,
    )

    token = current_language.set("ru")
    try:
        answered = json.loads(await runtime.invoke(say("Listing connections"), work))
    finally:
        current_language.reset(token)

    assert answered == {
        "model": "Allow",
        "person": "Разрешить",
        "substep": "Инструкция 1 · succeeded · строк: 3",
    }
