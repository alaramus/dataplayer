"""What a ZooKeeper connection can be asked to do to its znodes (D300).

Making one at the top or under the selected znode, deleting one with no
children, deleting one with everything under it after a preview, and changing
an ACL. A znode's data is written in its editor (D298), not here.

The catalog is a tree whose level is always its top, so every action is
offered there; those acting on a znode are switched on by the selection.
"""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from kazoo.client import KazooClient
from kazoo.exceptions import NoAuthError, NodeExistsError, NotEmptyError
from kazoo.security import ACL, Id
from pydantic import BaseModel, Field, field_validator

from app.adapters.actions import (
    Action,
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActsOn,
    FieldHints,
    JsonAction,
)
from app.adapters.catalog import NodeKind
from app.adapters.layout import layout
from app.adapters.zookeeper.options import ZookeeperDigest
from app.adapters.zookeeper.session import ZookeeperSession
from app.adapters.zookeeper.znodes import SYSTEM_ROOT, checked_path, child_path, name_of
from app.core.translation import N_, say

# How much data a form may write: ZooKeeper's own default ceiling on a packet.
MAX_DATA = 1_000_000

# Past this many znodes a subtree is not deleted or re-ACLed from a form: one
# request walks it, and zkCli's deleteall is the tool for a larger one.
SUBTREE_CEILING = 10_000

# How many paths a preview names before it says how many more there are.
PREVIEW_PATHS = 20

# ZooKeeper's permission letters in the order zkCli prints them, with the bit
# each one is.
LETTERS: tuple[tuple[str, int], ...] = (
    ("c", 4),
    ("d", 8),
    ("r", 1),
    ("w", 2),
    ("a", 16),
)
ADMIN = 16


def _name_check(name: str) -> str:
    """A znode's own name: one segment of a path, as ZooKeeper takes it."""
    if name in {"", ".", ".."} or "/" in name:
        raise ValueError(
            say("A znode name is one part of a path: no /, and not . or ..")
        )
    if any(char < " " or char == "\x7f" for char in name):
        raise ValueError(say("A znode name holds no control characters"))
    return name


def parent_of(path: str) -> str | None:
    """The catalog id to read again when a znode under it changed; None is the top."""
    head = path.rsplit("/", 1)[0]
    return head or None


def is_system(path: str) -> bool:
    return path == SYSTEM_ROOT or path.startswith(SYSTEM_ROOT + "/")


# --- the ACL, written the way zkCli writes it ---------------------------------


def acl_text(entries: Sequence[Any]) -> str:
    """One `scheme:id:perms` per line, as `getAcl` prints them."""
    lines = []
    for entry in entries:
        perms = int(entry.perms)
        letters = "".join(letter for letter, bit in LETTERS if perms & bit)
        lines.append(f"{entry.id.scheme}:{entry.id.id}:{letters}")
    return "\n".join(lines)


def parse_acl(text: str) -> list[ACL]:
    """`scheme:id:perms` per line; the id may hold colons, as a digest's does."""
    entries: list[ACL] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line == "":
            continue
        scheme, _, rest = line.partition(":")
        ident, _, letters = rest.rpartition(":")
        if scheme == "" or _ == "" or letters == "":
            raise ValueError(
                say('Write each line as scheme:id:permissions, not "{line}"', line=line)
            )
        unknown = set(letters) - {letter for letter, _bit in LETTERS}
        if unknown or len(set(letters)) != len(letters):
            raise ValueError(
                say(
                    'Permissions are letters from cdrwa, each once, not "{letters}"',
                    letters=letters,
                )
            )
        perms = sum(bit for letter, bit in LETTERS if letter in letters)
        entries.append(ACL(perms, Id(scheme, ident)))
    if not entries:
        raise ValueError(say("An ACL needs at least one line"))
    return entries


def keeps_admin(entries: Sequence[ACL], user: str | None) -> bool:
    """Whether this connection could still change the ACL after it is set.

    Read from what the connection is known to be: anyone, the session's own
    identities, or the digest user it signs in as. An `ip` entry may well be
    this server too, which is why the answer is a warning and never a refusal.
    """
    for entry in entries:
        if not entry.perms & ADMIN:
            continue
        scheme, ident = entry.id.scheme, entry.id.id
        if (scheme, ident) == ("world", "anyone") or scheme == "auth":
            return True
        if user is not None and scheme == "digest" and ident.split(":", 1)[0] == user:
            return True
    return False


# --- walking a subtree -------------------------------------------------------


def subtree(client: KazooClient, path: str) -> list[str]:
    """Every znode under `path`, deepest first, `path` itself last.

    Refused past the ceiling, and refused where a child may not be listed:
    a subtree that could not be read whole cannot be said to be deleted.
    """
    found: list[str] = []
    pending = [path]
    while pending:
        here = pending.pop()
        found.append(here)
        if len(found) > SUBTREE_CEILING:
            raise ActionRefused(
                "too_large",
                say(
                    "More than {count} znodes are under this one; delete it with deleteall in zkCli",
                    count=SUBTREE_CEILING,
                ),
            )
        try:
            names = client.get_children(here)
        except NoAuthError:
            raise ActionRefused(
                "not_applicable",
                say("This connection may not list what is under {path}", path=here),
            ) from None
        pending.extend(child_path(here, name) for name in sorted(names, reverse=True))
    found.sort(key=lambda one: one.count("/"), reverse=True)
    return found


def named(paths: Sequence[str]) -> list[str]:
    """The first paths of a preview, and how many more there are."""
    lines = list(paths[:PREVIEW_PATHS])
    if len(paths) > PREVIEW_PATHS:
        lines.append(say("and {count} more", count=len(paths) - PREVIEW_PATHS))
    return lines


# --- the forms ---------------------------------------------------------------


class NewZnodeParams(BaseModel):
    name: str = Field(
        title=N_("Name"),
        description=N_("One part of a path"),
        examples=["config"],
        max_length=255,
        json_schema_extra=layout(),
    )
    data: str = Field(
        default="",
        title=N_("Data"),
        description=N_("Stored as UTF-8 text; may be left empty"),
        examples=['{"replicas": 3}'],
        max_length=MAX_DATA,
        json_schema_extra=layout(multiline=True),
    )
    # A toggle rather than a choice of kinds: there are two, since an ephemeral
    # znode would end with this request's session (D300).
    sequential: bool = Field(
        default=False,
        title=N_("Sequential: ZooKeeper adds a ten-digit number to the name"),
    )

    _check_name = field_validator("name")(_name_check)


class NoParams(BaseModel):
    """Deleting says nothing but which znodes, and those are the selection."""


class AclParams(BaseModel):
    acl: str = Field(
        title=N_("ACL"),
        description=N_(
            "One entry per line as scheme:id:permissions, as zkCli writes them; "
            "permissions are letters from cdrwa — create, delete, read, write, admin"
        ),
        examples=["world:anyone:r\ndigest:ops:<hash>:cdrwa"],
        max_length=100_000,
        json_schema_extra=layout(multiline=True),
    )
    recursive: bool = Field(
        default=False,
        title=N_("Also every znode under it"),
    )

    @field_validator("acl")
    @classmethod
    def _parses(cls, text: str) -> str:
        parse_acl(text)
        return text


# --- the actions -------------------------------------------------------------


class _ZnodeAction:
    def __init__(self, session: ZookeeperSession) -> None:
        self._session = session

    def _target(self, node_id: str | None) -> str:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a znode first"))
        path = checked_path(node_id)
        if path == "/":
            raise ActionRefused(
                "not_applicable", say("The top of the tree is not a znode to change")
            )
        return path

    def _user(self) -> str | None:
        options = self._session.options
        return options.user if isinstance(options, ZookeeperDigest) else None


class _NewZnode(_ZnodeAction, JsonAction[NewZnodeParams]):
    params_model = NewZnodeParams

    def _parent(self, node_id: str | None) -> str:
        raise NotImplementedError

    async def run(self, node_id: str | None, params: NewZnodeParams) -> ActionResult:
        parent = self._parent(node_id)
        wanted = child_path(parent, params.name)

        def create(client: KazooClient) -> str:
            try:
                made: str = client.create(
                    wanted,
                    params.data.encode("utf-8"),
                    sequence=params.sequential,
                )
            except NodeExistsError:
                raise ActionRefused(
                    "conflict", say("A znode with that name already exists")
                ) from None
            return made

        made = await self._session.run(create, parent)
        return ActionResult(
            message=say("{name} created", name=name_of(made)),
            reload_node_ids=[None if parent == "/" else parent],
            created_node_id=made,
        )


class NewTopZnode(_NewZnode):
    """A znode at the top of the tree, or of the root path."""

    name: ClassVar[str] = "new_top_znode"
    title: ClassVar[str] = N_("New znode at the top")
    # The tree's level is its top, and nothing is a place below it (D298).
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"znode"})
    acts_on: ClassVar[ActsOn] = "level"

    def _parent(self, node_id: str | None) -> str:
        return "/" if node_id is None else checked_path(node_id)


class NewChildZnode(_NewZnode):
    """A znode under the selected one."""

    name: ClassVar[str] = "new_child_znode"
    title: ClassVar[str] = N_("New znode inside")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"znode"})
    acts_on: ClassVar[ActsOn] = "node"

    def _parent(self, node_id: str | None) -> str:
        return self._target(node_id)


class DeleteZnode(_ZnodeAction, JsonAction[NoParams]):
    """A znode with no children, at whatever version it is."""

    name: ClassVar[str] = "delete_znode"
    title: ClassVar[str] = N_("Delete")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"znode"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    bulk: ClassVar[bool] = True
    params_model = NoParams

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        del params
        path = self._target(node_id)

        def delete(client: KazooClient) -> None:
            try:
                client.delete(path)
            except NotEmptyError:
                raise ActionRefused(
                    "conflict",
                    say(
                        "{name} has children; use Delete with children",
                        name=name_of(path),
                    ),
                ) from None

        await self._session.run(delete, path)
        return ActionResult(
            message=say("{name} deleted", name=name_of(path)),
            reload_node_ids=[parent_of(path)],
        )


class DeleteSubtree(_ZnodeAction, JsonAction[NoParams]):
    """A znode and everything under it, after saying what that is."""

    name: ClassVar[str] = "delete_subtree"
    title: ClassVar[str] = N_("Delete with children")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"znode"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_(
        "This znode and every znode under it will be deleted. Delete them?"
    )
    params_model = NoParams

    def _guarded(self, node_id: str | None) -> str:
        path = self._target(node_id)
        if is_system(path):
            raise ActionRefused(
                "not_applicable", say("/zookeeper belongs to the server")
            )
        return path

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        self._validated(raw)
        path = self._guarded(node_id)
        paths = await self._session.run(lambda client: subtree(client, path), path)
        return ActionPreview(
            summary=say("{count} znodes will be deleted", count=len(paths)),
            items=named(paths),
        )

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        del params
        path = self._guarded(node_id)

        def delete(client: KazooClient) -> int:
            paths = subtree(client, path)
            # Deepest first, so each znode is empty when it is deleted; one
            # made meanwhile under it fails the parent's delete, and is said.
            for one in paths:
                try:
                    client.delete(one)
                except NotEmptyError:
                    raise ActionRefused(
                        "conflict",
                        say(
                            "A znode was made under {path} meanwhile; nothing above it was deleted",
                            path=one,
                        ),
                    ) from None
            return len(paths)

        count = await self._session.run(delete, path)
        return ActionResult(
            message=say("{count} znodes deleted", count=count),
            reload_node_ids=[parent_of(path)],
        )


class ChangeAcl(_ZnodeAction, JsonAction[AclParams]):
    """Who may do what to a znode, and to every znode under it if asked."""

    name: ClassVar[str] = "change_acl"
    title: ClassVar[str] = N_("Change ACL")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"znode"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_(
        "Whoever this ACL leaves out will no longer reach the znode. Change it?"
    )
    params_model = AclParams

    async def field_hints(self, node_id: str | None) -> FieldHints:
        path = self._target(node_id)
        entries, _ = await self._session.run(lambda client: client.get_acls(path), path)
        return FieldHints(values={"acl": acl_text(entries)})

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        params = self._validated(raw)
        path = self._target(node_id)
        entries = parse_acl(params.acl)
        count = 1
        if params.recursive:
            count = len(
                await self._session.run(lambda client: subtree(client, path), path)
            )
        items = [acl_text([entry]) for entry in entries]
        if not keeps_admin(entries, self._user()):
            items.append(
                say(
                    "Warning: this connection will not be able to change this ACL again"
                )
            )
        return ActionPreview(
            summary=say("The ACL of {count} znodes will be replaced with", count=count),
            items=items,
        )

    async def run(self, node_id: str | None, params: AclParams) -> ActionResult:
        path = self._target(node_id)
        entries = parse_acl(params.acl)

        def apply(client: KazooClient) -> int:
            # The deepest first, so that losing admin on a znode never stops
            # the ones under it from being reached.
            paths = subtree(client, path) if params.recursive else [path]
            for one in paths:
                client.set_acls(one, entries)
            return len(paths)

        count = await self._session.run(apply, path)
        return ActionResult(
            message=say("The ACL of {count} znodes changed", count=count),
            reload_node_ids=[parent_of(path)],
        )


# The order the menu shows them in.
ZOOKEEPER_ACTION_TYPES: tuple[
    type[NewTopZnode | NewChildZnode | DeleteZnode | DeleteSubtree | ChangeAcl], ...
] = (NewTopZnode, NewChildZnode, DeleteZnode, DeleteSubtree, ChangeAcl)


def build_actions(session: ZookeeperSession) -> list[Action[Any]]:
    return [action(session) for action in ZOOKEEPER_ACTION_TYPES]
