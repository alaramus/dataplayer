import json
import uuid
from unittest.mock import MagicMock

import pytest

from app.ai.tools import (
    MAX_RESULT_BYTES,
    MAX_TOOL_CALLS,
    ToolLimitReached,
    ToolRuntime,
    bounded_json,
    connector_id_from_result,
    transfer_refusal,
)
from app.connectors.models import Connector


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

    assert connector_id_from_result(json.dumps({"connector_id": str(connector_id)})) == connector_id
    assert connector_id_from_result(json.dumps({"connections": []})) is None
    assert connector_id_from_result("not json") is None


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
    assert connector_id_from_result(json.dumps(refusal)) is None


async def test_the_fifty_first_tool_call_is_refused_before_work_starts() -> None:
    async def ignored(*_args: object) -> None:
        return None

    runtime = ToolRuntime(
        run_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        resources=MagicMock(),
        say=ignored,
        opened=ignored,
        calls=MAX_TOOL_CALLS,
    )

    with pytest.raises(ToolLimitReached, match="50 tool calls"):
        await runtime.invoke("Too late", MagicMock())
