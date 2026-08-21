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
from collections.abc import Iterator, Mapping
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from app.adapters.catalog import NodeKind


class ActionResult(BaseModel):
    """What happened, and what the client should re-read because of it.

    Which branch of the catalog changed is known to whoever performed the
    action; deriving it on the client from the name of the action would put
    the same rule in two places.
    """

    message: str
    # The node whose children changed. None means the root of the connector.
    reload_node_id: str | None = None


# Why an action that is understood must still not be performed. Kept apart
# from AdapterError, which means the source itself failed: a taken name is not
# a failure of the file system, and answering 502 for it would be a lie.
RefusalReason = Literal["conflict", "not_applicable", "too_large"]


class ActionRefused(Exception):
    def __init__(self, reason: RefusalReason, message: str) -> None:
        super().__init__(message)
        self.reason: RefusalReason = reason
        self.message = message


class UnknownAction(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown action: {name}")
        self.name = name


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
    destructive: ClassVar[bool] = False

    params_model: type[P]

    def params_schema(self) -> dict[str, Any]:
        return self.params_model.model_json_schema()

    def _validated(self, raw: Mapping[str, Any]) -> P:
        return self.params_model.model_validate(raw)


class JsonAction[P: BaseModel](Action[P], ABC):
    """An action whose whole request is its parameters."""

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
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


@runtime_checkable
class SupportsActions(Protocol):
    """A source that can be asked to change something.

    Two questions, answered by the same driver: which actions this node admits,
    and which action a name refers to. Performing is done by calling the action
    itself, so there is no third place where a name could be resolved
    differently.
    """

    async def available(self, node_id: str | None) -> list[Action[Any]]: ...

    def action(self, name: str) -> Action[Any]: ...
