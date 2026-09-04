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
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.catalog import NodeKind
from app.core.access import Access


class NodeReplacement(BaseModel):
    old_node_id: str
    new_node_id: str
    title: str


class ActionResult(BaseModel):
    """What happened, and what the client should re-read because of it.

    Which branches of the catalog changed are known to whoever performed the
    action; deriving them on the client from the name of the action would put
    the same rule in two places.
    """

    message: str
    # Every node whose children changed. None means the root of the connector.
    # A move names both parents; making the client infer either one from the
    # moved node's opaque id would break D21.
    reload_node_ids: list[str | None]
    # A node whose source identity changed. Panels holding the old opaque id
    # replace it with the new one; the client never derives either id.
    replacement: NodeReplacement | None = None


class ActionDownloadMetadata(BaseModel):
    """The exact response metadata for bytes produced by an action."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)


@dataclass(frozen=True)
class ActionDownload:
    """One prepared action result, streamed without assembling it in memory."""

    metadata: ActionDownloadMetadata
    body: AsyncIterator[bytes]


class ActionDownloadReady(BaseModel):
    """A short-lived native-browser route for one action invocation."""

    download_url: str


class ConnectorDraft(BaseModel):
    """Source-provided values for a new connector form; nothing is saved yet."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    adapter_type: str = Field(min_length=1, max_length=64)
    options: dict[str, Any]


# Why an action that is understood must still not be performed. Kept apart
# from AdapterError, which means the source itself failed: a taken name is not
# a failure of the file system, and answering 502 for it would be a lie.
RefusalReason = Literal["conflict", "not_applicable", "too_large"]

# What an action changes: an explicitly selected node, a shown place's
# children, or the catalog level itself. A client has to tell the three apart
# to know what to send an action, and reading it off the names would mean
# teaching the client every action that is ever added (D56).
ActsOn = Literal["node", "children", "level"]


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
    # of that node it changes. `level` is the catalog level itself, kept apart
    # from a selected grouping whose children happen to be shown in it.
    acts_on: ClassVar[ActsOn]
    destructive: ClassVar[bool] = False
    # What the confirmation asks, when "are you sure you want to delete this"
    # is not what is about to happen. Every destructive action there was until
    # now removed something outright, so the client wrote that sentence
    # itself; setting an expiry is destructive and is not a deletion, and only
    # the action knows the difference. `None` keeps the client's own wording,
    # which names the node.
    question: ClassVar[str | None] = None
    # What a caller must hold on the connection to run this. Declared on the
    # class beside `destructive` because it is the same sort of statement, and
    # defaulting to `write` so that an action which says nothing about itself
    # is not thereby free to anyone who can read.
    requires: ClassVar[Access] = "write"
    # Whether one filled form may be applied to a set of nodes at all.
    # Renaming five files to one name is not five renames, and nothing in the
    # shape of an action says so — only the action itself knows. How a set is
    # then carried out is a separate question, answered by `TakesNodeSet`:
    # this only says a set is allowed.
    bulk: ClassVar[bool] = False
    # Whether one filled form may be carried by several files at once.
    # Declared beside bulk because it is the same sort of statement about a
    # set, and declared rather than derived because the transport is one
    # file per request either way: there is no second method for an
    # isinstance check to find. Five files into a folder are five uploads;
    # a table loaded from a CSV is one file, and a second would be a second
    # table.
    many_files: ClassVar[bool] = False

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


@runtime_checkable
class TakesNodeSet(Protocol):
    """An action performed on a whole selection at once, in one request.

    The other half of `bulk`, which only says a set is allowed. Repeating one
    filled form per node is right while the nodes are independent: five files
    deleted from a folder are five deletions, and a refusal of one says
    nothing about the other four.

    It is wrong when the set is the question. Three relations that depend on
    each other are dropped by one statement and refused by three, in an order
    the client happened to send them in — so an action whose answer is about
    the whole selection receives the whole selection, and what it does with it
    is one thing that either happens or does not.
    """

    async def perform_on_set(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionResult: ...


@runtime_checkable
class ProducesDownload(Protocol):
    """An action whose result is a download over its whole target set.

    This is a transport of an action, like JSON or multipart upload, not a
    property of a catalog node. The source owns both the selection semantics
    and the bytes: one adapter may return an original object while another
    may build an archive or export through the same client command.

    The filled form comes with it, because a download may be a choice as well
    as a selection — which format to write the answer in — and validating it
    is the action's own job, exactly as it is for `perform`.
    """

    async def download(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionDownload: ...


@runtime_checkable
class PreparesConnector(Protocol):
    """An action that opens a connector form with source-resolved options."""

    async def prepare_connector(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ConnectorDraft: ...


class ActionPreview(BaseModel):
    """What an action would do, asked of the source before it is done.

    Every line of it is the source's own answer. The screen renders a sentence
    and a list and knows nothing about what is being previewed — which is what
    lets one dialog show the consequences of a cascade without any part of the
    client learning what a cascade is.

    Asked again whenever the form changes, because the answer depends on the
    parameters: the whole point of it is that ticking a box changes what would
    happen.
    """

    model_config = ConfigDict(extra="forbid")

    # One sentence about the whole thing.
    summary: str
    # A line per thing that would happen, in the source's words.
    items: list[str] = Field(default_factory=list)
    # True when the action cannot be performed as the form now stands. A
    # statement rather than an error: the request to look was answered, and
    # what it says is that the other request would not be.
    blocked: bool = False


@runtime_checkable
class Previews(Protocol):
    """An action that can be asked what it would do first.

    A capability of the action rather than a flag on it, checked the way
    `TakesFile` is, so what the API says about an action cannot drift from what
    the action does. Most actions have nothing worth previewing: a folder that
    is about to be created is described entirely by the name in the form.

    Raises the same things `perform` raises, since it is the same request
    asked in the subjunctive: ActionRefused for what may not be done at all,
    ValueError for a request that is wrong about the node.
    """

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview: ...


@runtime_checkable
class PreviewsSet(Protocol):
    """A set action that can be asked what it would do to the whole selection.

    Separate from `Previews` because it answers a different question: not
    "what would this do to that node" repeated, but one account of one thing.
    An action may take a set and have nothing worth previewing about it, so
    the two are declared apart, as `Previews` and `TakesParams` are.
    """

    async def preview_on_set(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionPreview: ...


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
    requires: Access


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
