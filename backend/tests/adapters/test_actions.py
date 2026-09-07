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
    action_availability,
)


class Named(BaseModel):
    name: str


class CreateThing(JsonAction[Named]):
    name = "create_thing"
    title = "Create a thing"
    applies_to = frozenset({"directory"})
    acts_on = "children"
    params_model = Named

    def __init__(self) -> None:
        self.seen: Named | None = None

    async def run(self, node_id: str | None, params: Named) -> ActionResult:
        self.seen = params
        return ActionResult(message="done", reload_node_ids=[node_id])


class DropThing(JsonAction[BaseModel]):
    name = "drop_thing"
    title = "Drop a thing"
    applies_to = frozenset({"directory", "file"})
    acts_on = "node"
    destructive = True
    bulk = True
    params_model = BaseModel

    async def run(self, node_id: str | None, params: BaseModel) -> ActionResult:
        return ActionResult(message="dropped", reload_node_ids=[None])


class PutThing(FileAction[Named]):
    name = "put_thing"
    title = "Put a thing"
    applies_to = frozenset({"directory"})
    acts_on = "children"
    params_model = Named

    async def run(
        self, node_id: str | None, params: Named, payload: FilePayload
    ) -> ActionResult:
        body = await payload.read(1024)
        return ActionResult(message=body.decode(), reload_node_ids=[node_id])


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
    result: ActionResult = ActionResult(message="done", reload_node_ids=["reports"])

    assert result.reload_node_ids == ["reports"]


def test_an_action_declares_whether_it_destroys_anything() -> None:
    by_name: dict[str, Any] = {action.name: action for action in action_set()}

    assert by_name["drop_thing"].destructive is True
    assert by_name["create_thing"].destructive is False


# --- what a set of nodes has in common ---------------------------------------


def test_selection_actions_must_be_shared_and_admit_multiple_targets() -> None:
    create, drop, put = CreateThing(), DropThing(), PutThing()
    offers = [[create, drop, put], [drop, put]]
    admitted = [
        action.name
        for action in (create, drop, put)
        if action_availability(action, ["one", "two"], offers).applicable
    ]
    assert admitted == ["drop_thing"]


def test_available_targets_keep_request_order_despite_offer_order() -> None:
    create, drop, put = CreateThing(), DropThing(), PutThing()
    answer = action_availability(
        drop, ["two", "one"], [[create, drop, put], [put, drop, create]]
    )
    assert answer.available_node_ids == ["two", "one"]


def test_an_action_that_did_not_declare_bulk_is_refused_for_multiple_targets() -> None:
    action = CreateThing()
    answer = action_availability(action, ["one", "two"], [[action], [action]])
    assert not answer.applicable
    assert answer.unavailable_reason == "Select one target to use this"


def test_no_action_is_available_for_an_empty_selection() -> None:
    assert not action_availability(DropThing(), [], []).applicable


def test_an_action_declares_what_it_changes() -> None:
    """The node it is given, or what is inside it.

    Renaming changes the node; creating a folder changes what the node holds.
    A client acting on a set of ticked rows has to tell the two apart without
    knowing the name of a single action, so the action says which it is.
    """
    by_name: dict[str, Any] = {action.name: action for action in action_set()}

    assert by_name["drop_thing"].acts_on == "node"
    assert by_name["create_thing"].acts_on == "children"


def test_an_action_declares_whether_it_applies_to_many_at_once() -> None:
    by_name: dict[str, Any] = {action.name: action for action in action_set()}

    assert by_name["drop_thing"].bulk is True
    assert by_name["create_thing"].bulk is False


class ChooseDestination(CreateThing):
    acts_on = "destination"


class RenameGrouping(CreateThing):
    acts_on = "group"


def test_a_destination_is_a_choice_even_when_some_candidates_refuse_it() -> None:
    action = ChooseDestination()
    answer = action_availability(action, ["system", "one", "two"], [[], [action], [action]])
    assert answer.applicable
    assert answer.available_node_ids == ["one", "two"]
    assert answer.unavailable_reason is None


@pytest.mark.parametrize("scope", [ChooseDestination, RenameGrouping, DropThing])
def test_no_targets_never_enable_an_action(scope: type[JsonAction[Any]]) -> None:
    assert not action_availability(scope(), [], []).applicable


def test_a_grouping_rename_requires_one_target_even_when_both_qualify() -> None:
    action = RenameGrouping()
    answer = action_availability(action, ["one", "two"], [[action], [action]])
    assert not answer.applicable
    assert answer.unavailable_reason == "Select one grouping to use this"
    assert action_availability(action, ["one"], [[action]]).applicable


def test_bulk_actions_never_silently_drop_an_ineligible_target() -> None:
    action = DropThing()
    refused = action_availability(action, ["one", "root"], [[action], []])
    assert not refused.applicable
    assert refused.available_node_ids == ["one"]
    assert refused.unavailable_reason == "This action is not available for every selected target"
    assert action_availability(action, ["one", "two"], [[action], [action]]).applicable


def test_single_target_creation_and_null_root_remain_distinct_from_a_batch() -> None:
    action = CreateThing()
    root = action_availability(action, [None], [[action]])
    assert root.applicable
    assert root.available_node_ids == [None]
    batch = action_availability(action, ["one", "two"], [[action], [action]])
    assert not batch.applicable
    assert batch.unavailable_reason == "Select one target to use this"
