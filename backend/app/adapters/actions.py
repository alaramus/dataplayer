"""What a source can be asked to do, and the only way to ask it.

An action is one object holding its name, its parameter model and its
implementation together. That is the whole point of this module: in the old
application the list of supported actions and the thing that dispatched them
were separate — a 765-line table of names next to
`getattr(connector, action)(**request_body)` guarded by `hasattr`. The table
never took part in the guard, so any public method of a driver was callable by
name, and any method could be added without ever being declared. Here the
declaration *is* the callable, and a name that is not in the set does not
resolve.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from app.adapters.catalog import NodeKind
from app.core.access import Access


class NodeReplacement(BaseModel):
    old_node_id: str
    new_node_id: str
    title: str


class ActionResult(BaseModel):
    """What happened, and what the client should re-read because of it.

    Which branch of the catalog changed is known to whoever performed the
    action; deriving it on the client from the name of the action would put
    the same rule in two places.
    """

    message: str
    # The node whose children changed. None means the root of the connector.
    reload_node_id: str | None = None
    # A node whose source identity changed. Panels holding the old opaque id
    # replace it with the new one; the client never derives either id.
    replacement: NodeReplacement | None = None


# Why an action that is understood must still not be performed. Kept apart
# from AdapterError, which means the source itself failed: a taken name is not
# a failure of the file system, and answering 502 for it would be a lie.
RefusalReason = Literal["conflict", "not_applicable", "too_large"]

# What an action changes: the node it is given, or what that node holds.
# Renaming and deleting are done to the rows a user ticked; a new folder and an
# upload are made inside the level being looked at. A client has to tell the
# two apart to know what to send an action, and reading it off the names would
# mean teaching the client every action that is ever added.
ActsOn = Literal["node", "children"]


class ActionRefused(Exception):
    def __init__(self, reason: RefusalReason, message: str) -> None:
        super().__init__(message)
        self.reason: RefusalReason = reason
        self.message = message


class UnknownAction(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown action: {name}")
        self.name = name


# How much of an upload is taken at a time. Big enough that a large file is
# not a million round trips, small enough that a refused one is caught long
# before it is all in memory. Beside `FilePayload` rather than in one adapter,
# because both sources that read an upload read it the same way.
CHUNK_BYTES = 64 * 1024


class FilePayload(Protocol):
    """The bytes of an upload, read in chunks.

    Declared here rather than taken as `fastapi.UploadFile` so that a driver
    stays free of the web framework and a test can hand an action ten bytes
    without one.
    """

    filename: str | None

    async def read(self, size: int) -> bytes: ...


class Action[P: BaseModel](ABC):
    """Everything an action declares about itself, plus its own validation.

    A class rather than a Protocol because it carries behaviour that must not
    be reimplemented per action: parameters are validated by the action's own
    model before its body runs. The inheritance rejected in decision D2b was a
    chain of drivers growing along several axes at once; this base has one
    responsibility and no axis to grow along.
    """

    name: ClassVar[str]
    title: ClassVar[str]
    # Which kinds of catalog node the action makes sense for. Whether it is
    # allowed on one particular node — the root of a connector, say — is a
    # question of state and belongs to the driver.
    applies_to: ClassVar[frozenset[NodeKind]]
    # Declared beside applies_to because it is the same sort of statement: one
    # says which kinds of node an action makes sense for, the other says what
    # of that node it changes.
    acts_on: ClassVar[ActsOn]
    destructive: ClassVar[bool] = False
    # What a caller must hold on the connection to run this. Declared on the
    # class beside `destructive` because it is the same sort of statement, and
    # defaulting to `write` so that an action which says nothing about itself
    # is not thereby free to anyone who can read.
    requires: ClassVar[Access] = "write"
    # Whether one filled form may be applied to a set of nodes. Renaming five
    # files to one name is not five renames, and nothing in the shape of an
    # action says so — only the action itself knows.
    bulk: ClassVar[bool] = False

    params_model: type[P]

    def params_schema(self) -> dict[str, Any]:
        return self.params_model.model_json_schema()

    def _validated(self, raw: Mapping[str, Any]) -> P:
        return self.params_model.model_validate(raw)


class JsonAction[P: BaseModel](Action[P], ABC):
    """An action whose whole request is its parameters."""

    async def perform(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionResult:
        return await self.run(node_id, self._validated(raw))

    @abstractmethod
    async def run(self, node_id: str | None, params: P) -> ActionResult: ...


class FileAction[P: BaseModel](Action[P], ABC):
    """An action that cannot be performed without a file to carry."""

    async def perform_with_file(
        self, node_id: str | None, raw: Mapping[str, Any], payload: FilePayload
    ) -> ActionResult:
        return await self.run(node_id, self._validated(raw), payload)

    @abstractmethod
    async def run(
        self, node_id: str | None, params: P, payload: FilePayload
    ) -> ActionResult: ...


@runtime_checkable
class TakesParams(Protocol):
    """Callable with a JSON body and nothing else."""

    async def perform(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionResult: ...


@runtime_checkable
class TakesFile(Protocol):
    """Callable only with a file attached.

    A route checks for this instead of reading a declared flag, so what the
    API says about an action cannot drift from what the action does.
    """

    async def perform_with_file(
        self, node_id: str | None, raw: Mapping[str, Any], payload: FilePayload
    ) -> ActionResult: ...


class ActionSet:
    """The actions one driver offers, addressed by name."""

    def __init__(self, actions: list[Action[Any]]) -> None:
        self._by_name = {action.name: action for action in actions}

    def __iter__(self) -> Iterator[Action[Any]]:
        return iter(self._by_name.values())

    def get(self, name: str) -> Action[Any]:
        try:
            return self._by_name[name]
        except KeyError:
            raise UnknownAction(name) from None

    def for_kind(self, kind: NodeKind) -> list[Action[Any]]:
        return [action for action in self if kind in action.applies_to]


def common_actions(
    offers: Sequence[Sequence[Action[Any]]], *, bulk_only: bool
) -> list[Action[Any]]:
    """What every node in a set admits, in the order the driver gave them.

    A set of nodes is asked about in one call, so the intersection is taken
    here rather than by the client: which actions a node admits depends on its
    state, and a client that guessed would offer what the server refuses.
    """
    if not offers:
        return []
    shared = set[str].intersection(
        *({action.name for action in group} for group in offers)
    )
    return [
        action
        for action in offers[0]
        if action.name in shared and (action.bulk or not bulk_only)
    ]


@runtime_checkable
class SupportsActions(Protocol):
    """A source that can be asked to change something.

    Three questions, answered by the same driver: everything it can do, which
    of that this node admits, and which action a name refers to. Performing is
    done by calling the action itself, so there is no fourth place where a name
    could be resolved differently — and what a client is allowed to do is still
    decided by `available`, never by the vocabulary.
    """

    async def available(self, node_id: str | None) -> list[Action[Any]]: ...

    def action(self, name: str) -> Action[Any]: ...

    def all_actions(self) -> list[Action[Any]]: ...


class ActionType(Protocol):
    """An action seen as a class: what it is called, before one is built.

    `name` and `title` are `ClassVar` on `Action`, so they can be read without
    a session — which is the whole point, since the catalog asks what a type
    of source can do while no connector exists.
    """

    name: str
    title: str


@runtime_checkable
class DeclaresActions(Protocol):
    """A driver that names its action classes without being built.

    Separate from `SupportsActions`, which is about an instance: `available`
    needs a session to look at a node with.

    A classmethod and not a `ClassVar` on purpose: a protocol holding data
    cannot be used with `issubclass`, and reaching for the attribute with
    `getattr` would be the `hasattr` dispatch this module was written to
    remove.
    """

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]: ...
