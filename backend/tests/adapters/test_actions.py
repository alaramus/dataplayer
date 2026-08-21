"""The vocabulary of actions, exercised through actions of its own."""

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.adapters.actions import (
    ActionRefused,
    ActionResult,
    ActionSet,
    FileAction,
    FilePayload,
    JsonAction,
    TakesFile,
    TakesParams,
    UnknownAction,
)


class Named(BaseModel):
    name: str


class CreateThing(JsonAction[Named]):
    name = "create_thing"
    title = "Create a thing"
    applies_to = frozenset({"directory"})
    params_model = Named

    def __init__(self) -> None:
        self.seen: Named | None = None

    async def run(self, node_id: str | None, params: Named) -> ActionResult:
        self.seen = params
        return ActionResult(message="done", reload_node_id=node_id)


class DropThing(JsonAction[BaseModel]):
    name = "drop_thing"
    title = "Drop a thing"
    applies_to = frozenset({"directory", "file"})
    destructive = True
    params_model = BaseModel

    async def run(self, node_id: str | None, params: BaseModel) -> ActionResult:
        return ActionResult(message="dropped", reload_node_id=None)


class PutThing(FileAction[Named]):
    name = "put_thing"
    title = "Put a thing"
    applies_to = frozenset({"directory"})
    params_model = Named

    async def run(
        self, node_id: str | None, params: Named, payload: FilePayload
    ) -> ActionResult:
        body = await payload.read(1024)
        return ActionResult(message=body.decode(), reload_node_id=node_id)


class Bytes:
    """The smallest thing that satisfies FilePayload."""

    def __init__(self, body: bytes, filename: str | None = "thing.txt") -> None:
        self.filename = filename
        self._body = body

    async def read(self, size: int) -> bytes:
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


async def test_params_reach_the_action_as_its_own_model() -> None:
    action = CreateThing()

    await action.perform("reports", {"name": "q3"})

    assert action.seen == Named(name="q3")


async def test_params_that_miss_the_schema_never_reach_the_action() -> None:
    action = CreateThing()

    with pytest.raises(ValidationError):
        await action.perform("reports", {})

    assert action.seen is None


def test_the_schema_of_the_parameters_comes_from_the_model() -> None:
    schema = CreateThing().params_schema()

    assert set(schema["properties"]) == {"name"}


async def test_an_action_taking_a_file_is_told_apart_by_its_protocol() -> None:
    """The transport is derived, not declared twice.

    A hand-written flag could disagree with the implementation; a protocol
    check cannot.
    """
    assert isinstance(PutThing(), TakesFile)
    assert not isinstance(CreateThing(), TakesFile)


async def test_an_action_taking_a_file_cannot_be_called_without_one() -> None:
    assert not isinstance(PutThing(), TakesParams)
    assert isinstance(CreateThing(), TakesParams)


async def test_a_file_action_validates_its_parameters_too() -> None:
    action = PutThing()

    with pytest.raises(ValidationError):
        await action.perform_with_file("reports", {}, Bytes(b"hello"))


async def test_a_file_action_receives_the_payload() -> None:
    result = await PutThing().perform_with_file(
        "reports", {"name": "greeting"}, Bytes(b"hello")
    )

    assert result.message == "hello"


def action_set() -> ActionSet:
    return ActionSet([CreateThing(), DropThing(), PutThing()])


def test_only_declared_actions_can_be_reached() -> None:
    """The registry holds the objects, so nothing undeclared is callable."""
    with pytest.raises(UnknownAction):
        action_set().get("shutdown")


def test_an_action_is_looked_up_by_name() -> None:
    assert isinstance(action_set().get("drop_thing"), DropThing)


def test_actions_are_offered_by_the_kind_of_node_they_apply_to() -> None:
    names = [action.name for action in action_set().for_kind("file")]

    assert names == ["drop_thing"]


def test_a_refusal_carries_the_reason_it_was_refused() -> None:
    refusal = ActionRefused("conflict", "That name is taken")

    assert refusal.reason == "conflict"
    assert str(refusal) == "That name is taken"


def test_the_result_says_which_branch_to_reload() -> None:
    result: ActionResult = ActionResult(message="done", reload_node_id="reports")

    assert result.reload_node_id == "reports"


def test_an_action_declares_whether_it_destroys_anything() -> None:
    by_name: dict[str, Any] = {action.name: action for action in action_set()}

    assert by_name["drop_thing"].destructive is True
    assert by_name["create_thing"].destructive is False
