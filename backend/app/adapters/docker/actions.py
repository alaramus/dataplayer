"""What a Docker connection can be asked to do (D410, D411).

A container's lifecycle — start, stop, restart, pause, unpause, kill — on one
container or a Compose project's; removing containers, images, volumes and
networks after saying what goes with them; pruning a group; making a volume or
a network. Pull and commit take minutes and are jobs (`jobs.py`, D412).

Whether a container is already as asked is decided from what was read, not
left to the daemon: it answers 304 to a second start or stop, but 409 to a
second pause and 500 to unpausing a running container (*checked*, Engine 29).
"""

import json
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from app.adapters.actions import (
    Action,
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActsOn,
    JsonAction,
    NodeRefusal,
)
from app.adapters.catalog import NodeKind
from app.adapters.docker.catalog import (
    VOLUME_NAME,
    Named,
    image_title,
    leaf_id,
    parse,
    project_id,
    project_of,
)
from app.adapters.docker.inventory import (
    BUILT_IN_NETWORKS,
    labels_of,
    name_of,
    read_containers,
    read_images,
    read_networks,
    read_volumes,
    users_of_image,
    users_of_network,
    users_of_volume,
)
from app.adapters.docker.session import DockerSession, segment
from app.adapters.layout import layout
from app.adapters.protocol import NodeNotFound
from app.core.access import Access
from app.core.translation import N_, say

# How many names a preview lists before it counts the rest.
PREVIEW_NAMES = 20
# How long a stop or a restart waits before killing, at most.
MAX_TIMEOUT = 600
ANONYMOUS_VOLUME = "com.docker.volume.anonymous"

type Container = dict[str, Any]


def listed(names: list[str]) -> list[str]:
    lines = names[:PREVIEW_NAMES]
    if len(names) > PREVIEW_NAMES:
        lines.append(say("and {count} more", count=len(names) - PREVIEW_NAMES))
    return lines


def size_text(total: int) -> str:
    value = float(total)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{total} B"  # pragma: no cover - the loop always returns


# --- the forms -----------------------------------------------------------------


class NoParams(BaseModel):
    """The selection says everything."""


class TimeoutParams(BaseModel):
    timeout: int | None = Field(
        default=None,
        ge=0,
        le=MAX_TIMEOUT,
        title=N_("Seconds to wait before killing"),
        description=N_("Empty for the daemon's own default, usually ten"),
        json_schema_extra=layout(),
    )


Signal = Literal["SIGTERM", "SIGKILL", "SIGINT", "SIGHUP"]


class KillParams(BaseModel):
    signal: Signal = Field(default="SIGKILL", title=N_("Signal"), json_schema_extra=layout())


class RemoveContainerParams(BaseModel):
    force: bool = Field(default=False, title=N_("Force: remove it even while it runs"))
    volumes: bool = Field(default=False, title=N_("Remove its anonymous volumes too"))


class RemoveImageParams(BaseModel):
    force: bool = Field(
        default=False, title=N_("Force: remove it even while stopped containers use it")
    )


class PruneImagesParams(BaseModel):
    all_unused: bool = Field(
        default=False,
        title=N_("Every image no container uses, not only untagged ones"),
    )


class PruneVolumesParams(BaseModel):
    named_too: bool = Field(
        default=False,
        title=N_("Named volumes too, not only anonymous ones"),
    )


class NewVolumeParams(BaseModel):
    name: str = Field(
        pattern=VOLUME_NAME,
        max_length=255,
        title=N_("Name"),
        description=N_("Letters, digits, _ . and -, starting with a letter or a digit"),
        examples=["app-data"],
        json_schema_extra=layout(),
    )


class NewNetworkParams(BaseModel):
    name: str = Field(
        pattern=VOLUME_NAME,
        max_length=255,
        title=N_("Name"),
        description=N_("Letters, digits, _ . and -, starting with a letter or a digit"),
        examples=["backend"],
        json_schema_extra=layout(),
    )
    internal: bool = Field(
        default=False, title=N_("Internal: no way out to other networks")
    )


# --- what a node id stands for -------------------------------------------------


async def containers_of(session: DockerSession, node_id: str | None) -> list[Container]:
    """The containers a lifecycle action acts on: one, or a Compose project's."""
    if node_id is None:
        raise ActionRefused("not_applicable", say("Choose a container or a Compose project"))
    named = parse(node_id)
    everything = (await read_containers(session)).items
    if named.leaf == "container" and named.view is None:
        found = [one for one in everything if one.get("Id") == named.key]
        if not found:
            raise NodeNotFound(node_id)
        return found
    if named.group == "containers" and named.project:
        found = [one for one in everything if project_of(one) == named.project]
        if not found:
            raise NodeNotFound(node_id)
        return found
    raise ActionRefused("not_applicable", say("Choose a container or a Compose project"))


def parent_of(container: Container) -> str:
    return project_id(project_of(container))


# --- a container's lifecycle (D410) --------------------------------------------


class _Lifecycle[P: BaseModel](JsonAction[P]):
    """One verb of a container's lifecycle, on each container of the target."""

    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"container", "directory"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "write"
    bulk: ClassVar[bool] = True
    # Over a container's view as well; a project has none (D424).
    in_view: ClassVar[bool] = True
    # The daemon's path after the container's.
    verb: ClassVar[str]
    # States it acts on; states it leaves as they are because they already are.
    acts_in: ClassVar[frozenset[str]]
    already_in: ClassVar[frozenset[str]] = frozenset()
    will: ClassVar[str]
    already: ClassVar[str]
    cannot: ClassVar[str]

    def __init__(self, session: DockerSession) -> None:
        self._session = session

    def _query(self, params: P) -> dict[str, str]:
        del params
        return {}

    def _sorted(self, containers: list[Container]) -> tuple[list[Container], list[Container], list[Container]]:
        acting, already, refused = [], [], []
        for one in containers:
            state = str(one.get("State") or "")
            if state in self.acts_in:
                acting.append(one)
            elif state in self.already_in:
                already.append(one)
            else:
                refused.append(one)
        return acting, already, refused

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        self._validated(raw)
        acting, already, refused = self._sorted(await containers_of(self._session, node_id))
        items = [say(self.will, name=name_of(one)) for one in acting]
        items += [say(self.already, name=name_of(one)) for one in already]
        items += [say(self.cannot, name=name_of(one)) for one in refused]
        return ActionPreview(
            summary=say("{count} containers will change", count=len(acting)),
            items=listed(items),
            blocked=not acting,
        )

    async def run(self, node_id: str | None, params: P) -> ActionResult:
        containers = await containers_of(self._session, node_id)
        acting, already, refused = self._sorted(containers)
        if not acting:
            raise ActionRefused(
                "not_applicable",
                say(self.cannot, name=name_of(refused[0]))
                if refused
                else say(self.already, name=name_of(already[0])),
            )
        for one in acting:
            await self._session.send(
                "POST",
                f"/containers/{segment(str(one['Id']))}/{self.verb}",
                self._query(params),
                # 304 and 409 are the container changing meanwhile: as asked.
                expected=(204, 304, 409),
                seconds=MAX_TIMEOUT + 30,
            )
        return ActionResult(
            message=say(
                "Done for {done} containers; {already} already were",
                done=len(acting),
                already=len(already),
            )
            if already
            else say("Done for {done} containers", done=len(acting)),
            reload_node_ids=list[str | None](
                sorted({parent_of(one) for one in containers} | {"containers"})
            ),
            refused=[
                NodeRefusal(
                    node_id=leaf_id("container", str(one["Id"])),
                    message=say(self.cannot, name=name_of(one)),
                )
                for one in refused
            ],
        )


_RUNNING = frozenset({"running", "restarting"})
_STOPPED = frozenset({"exited", "created", "dead"})


class StartContainers(_Lifecycle[NoParams]):
    name: ClassVar[str] = "docker_start"
    title: ClassVar[str] = N_("Start")
    icon: ClassVar[str | None] = "play_arrow"
    params_model = NoParams
    verb = "start"
    acts_in = _STOPPED
    already_in = _RUNNING
    will = N_("{name} will start")
    already = N_("{name} is already running")
    cannot = N_("{name} is paused; unpause it instead")


class StopContainers(_Lifecycle[TimeoutParams]):
    name: ClassVar[str] = "docker_stop"
    title: ClassVar[str] = N_("Stop")
    icon: ClassVar[str | None] = "stop"
    params_model = TimeoutParams
    verb = "stop"
    acts_in = _RUNNING | {"paused"}
    already_in = _STOPPED
    will = N_("{name} will stop")
    already = N_("{name} is already stopped")
    cannot = N_("{name} cannot be stopped now")

    def _query(self, params: TimeoutParams) -> dict[str, str]:
        return {} if params.timeout is None else {"t": str(params.timeout)}


class RestartContainers(_Lifecycle[TimeoutParams]):
    name: ClassVar[str] = "docker_restart"
    title: ClassVar[str] = N_("Restart")
    icon: ClassVar[str | None] = "restart_alt"
    params_model = TimeoutParams
    verb = "restart"
    acts_in = _RUNNING | _STOPPED | {"paused"}
    will = N_("{name} will restart")
    already = N_("{name} will restart")
    cannot = N_("{name} cannot be restarted now")

    def _query(self, params: TimeoutParams) -> dict[str, str]:
        return {} if params.timeout is None else {"t": str(params.timeout)}


class PauseContainers(_Lifecycle[NoParams]):
    name: ClassVar[str] = "docker_pause"
    title: ClassVar[str] = N_("Pause")
    icon: ClassVar[str | None] = "pause"
    params_model = NoParams
    verb = "pause"
    acts_in = frozenset({"running"})
    already_in = frozenset({"paused"})
    will = N_("{name} will pause")
    already = N_("{name} is already paused")
    cannot = N_("{name} is not running")


class UnpauseContainers(_Lifecycle[NoParams]):
    name: ClassVar[str] = "docker_unpause"
    title: ClassVar[str] = N_("Unpause")
    icon: ClassVar[str | None] = "resume"
    params_model = NoParams
    verb = "unpause"
    acts_in = frozenset({"paused"})
    already_in = _RUNNING
    will = N_("{name} will be unpaused")
    already = N_("{name} is not paused")
    cannot = N_("{name} is not running")


class KillContainers(_Lifecycle[KillParams]):
    name: ClassVar[str] = "docker_kill"
    title: ClassVar[str] = N_("Kill")
    icon: ClassVar[str | None] = "dangerous"
    params_model = KillParams
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_(
        "The signal is sent at once, without waiting for anything. Send it?"
    )
    verb = "kill"
    acts_in = _RUNNING | {"paused"}
    already_in = _STOPPED
    will = N_("{name} will be sent the signal")
    already = N_("{name} is already stopped")
    cannot = N_("{name} is not running")

    def _query(self, params: KillParams) -> dict[str, str]:
        return {"signal": params.signal}


# --- removing (D411) -------------------------------------------------------------


class _Removal[P: BaseModel](JsonAction[P]):
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    destructive: ClassVar[bool] = True
    bulk: ClassVar[bool] = True
    leaf: ClassVar[str]

    def __init__(self, session: DockerSession) -> None:
        self._session = session

    def _named(self, node_id: str | None) -> Named:
        named = parse(node_id or "")
        if named.leaf != self.leaf or named.view is not None:
            raise ActionRefused("not_applicable", say("Choose what to remove"))
        return named

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        named = self._named(node_id)
        title, blocker, items = await self._judge(named, params)
        if blocker is not None:
            return ActionPreview(summary=blocker, items=listed(items), blocked=True)
        return ActionPreview(
            summary=say("{name} will be removed", name=title), items=listed(items)
        )

    async def run(self, node_id: str | None, params: P) -> ActionResult:
        named = self._named(node_id)
        title, blocker, _ = await self._judge(named, params)
        if blocker is not None:
            raise ActionRefused("conflict", blocker)
        await self._remove(named, params)
        return ActionResult(
            message=say("{name} removed", name=title), reload_node_ids=self._reload()
        )

    def _reload(self) -> list[str | None]:
        return [f"{self.leaf}s"]

    async def _judge(self, named: Named, params: P) -> tuple[str, str | None, list[str]]:
        """Its name, why it cannot go now if it cannot, and what goes with it."""
        raise NotImplementedError

    async def _remove(self, named: Named, params: P) -> None:
        raise NotImplementedError


class RemoveContainer(_Removal[RemoveContainerParams]):
    name: ClassVar[str] = "docker_remove_container"
    title: ClassVar[str] = N_("Remove container")
    icon: ClassVar[str | None] = "delete"
    in_view: ClassVar[bool] = True
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"container"})
    params_model = RemoveContainerParams
    leaf = "container"

    def _reload(self) -> list[str | None]:
        return ["containers"]

    async def _judge(
        self, named: Named, params: RemoveContainerParams
    ) -> tuple[str, str | None, list[str]]:
        [one] = await containers_of(self._session, leaf_id("container", named.key))
        title = name_of(one)
        items: list[str] = []
        mounts = [
            str(mount.get("Name"))
            for mount in one.get("Mounts") or []
            if isinstance(mount, dict) and mount.get("Type") == "volume"
        ]
        if mounts:
            items.append(
                say("Its volumes removed with it: {names}", names=", ".join(mounts))
                if params.volumes
                else say("Its volumes stay: {names}", names=", ".join(mounts))
            )
        if one.get("State") in {"running", "restarting", "paused"} and not params.force:
            return title, say(
                "{name} is running: stop it first, or remove it with Force", name=title
            ), items
        return title, None, items

    async def _remove(self, named: Named, params: RemoveContainerParams) -> None:
        status, _ = await self._session.send(
            "DELETE",
            f"/containers/{segment(named.key)}",
            {"force": str(params.force).lower(), "v": str(params.volumes).lower()},
            expected=(204, 404, 409),
        )
        if status == 409:
            raise ActionRefused(
                "conflict", say("It is running: stop it first, or remove it with Force")
            )


class RemoveImage(_Removal[RemoveImageParams]):
    name: ClassVar[str] = "docker_remove_image"
    title: ClassVar[str] = N_("Remove image")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"image"})
    params_model = RemoveImageParams
    leaf = "image"

    async def _users(self, image_id: str) -> list[Container]:
        return users_of_image((await read_containers(self._session)).items, image_id)

    async def _judge(
        self, named: Named, params: RemoveImageParams
    ) -> tuple[str, str | None, list[str]]:
        images = (await read_images(self._session)).items
        found = [one for one in images if one.get("Id") == named.key]
        if not found:
            raise NodeNotFound(leaf_id("image", named.key))
        title = image_title(found[0])
        users = await self._users(named.key)
        names = sorted(name_of(one) for one in users)
        running = [one for one in users if one.get("State") in {"running", "paused", "restarting"}]
        if running:
            return title, say(
                "Running containers use it: {names}",
                names=", ".join(sorted(name_of(one) for one in running)),
            ), names
        if users and not params.force:
            return title, say(
                "Containers use it: {names}; remove them first, or use Force",
                names=", ".join(names),
            ), names
        tags = [str(tag) for tag in found[0].get("RepoTags") or []]
        return title, None, [say("Its tags go with it: {tags}", tags=", ".join(tags))] if tags else []

    async def _remove(self, named: Named, params: RemoveImageParams) -> None:
        status, _ = await self._session.send(
            "DELETE",
            f"/images/{segment(named.key)}",
            {"force": str(params.force).lower()},
            expected=(200, 404, 409),
        )
        if status == 409:
            names = sorted(name_of(one) for one in await self._users(named.key))
            raise ActionRefused(
                "conflict",
                say("Containers use it: {names}", names=", ".join(names))
                if names
                else say("Another image depends on it"),
            )


class RemoveVolume(_Removal[NoParams]):
    name: ClassVar[str] = "docker_remove_volume"
    title: ClassVar[str] = N_("Remove volume")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"volume"})
    params_model = NoParams
    leaf = "volume"

    async def _judge(self, named: Named, params: NoParams) -> tuple[str, str | None, list[str]]:
        del params
        volumes = (await read_volumes(self._session)).items
        if not any(one.get("Name") == named.key for one in volumes):
            raise NodeNotFound(leaf_id("volume", named.key))
        users = users_of_volume((await read_containers(self._session)).items, named.key)
        if users:
            names = sorted(name_of(one) for one in users)
            return named.key, say(
                "Containers mount it: {names}", names=", ".join(names)
            ), names
        return named.key, None, [say("Everything stored in it is lost")]

    async def _remove(self, named: Named, params: NoParams) -> None:
        del params
        status, _ = await self._session.send(
            "DELETE", f"/volumes/{segment(named.key)}", expected=(204, 404, 409)
        )
        if status == 409:
            raise ActionRefused("conflict", say("A container mounts it now"))


class RemoveNetwork(_Removal[NoParams]):
    name: ClassVar[str] = "docker_remove_network"
    title: ClassVar[str] = N_("Remove network")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"network"})
    params_model = NoParams
    leaf = "network"

    async def _judge(self, named: Named, params: NoParams) -> tuple[str, str | None, list[str]]:
        del params
        networks = (await read_networks(self._session)).items
        found = [one for one in networks if one.get("Id") == named.key]
        if not found:
            raise NodeNotFound(leaf_id("network", named.key))
        title = str(found[0].get("Name"))
        if title in BUILT_IN_NETWORKS:
            return title, say("{name} is one of Docker's own networks", name=title), []
        users = users_of_network((await read_containers(self._session)).items, found[0])
        if users:
            names = sorted(name_of(one) for one in users)
            return title, say(
                "Containers are attached to it: {names}", names=", ".join(names)
            ), names
        return title, None, []

    async def _remove(self, named: Named, params: NoParams) -> None:
        del params
        # 403 is also the daemon's word for a network in use or built in; both
        # were ruled out above, so here it is a proxy's or a plugin's (D409).
        await self._session.send(
            "DELETE", f"/networks/{segment(named.key)}", expected=(204, 404)
        )


# --- pruning a group (D411) ------------------------------------------------------


class _Prune[P: BaseModel](JsonAction[P]):
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "level"
    requires: ClassVar[Access] = "structure"
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = N_(
        "Everything listed will be removed, and whatever became unused since too. Prune?"
    )
    group: ClassVar[str]
    kind: ClassVar[str]

    def __init__(self, session: DockerSession) -> None:
        self._session = session

    def _level(self, node_id: str | None) -> None:
        if node_id != self.group:
            raise ActionRefused("not_applicable", say("Prune from the group it empties"))

    async def _doomed(self, params: P) -> tuple[list[str], int | None]:
        """What would go, by name, and how much space that frees where known."""
        raise NotImplementedError

    def _filters(self, params: P) -> dict[str, list[str]]:
        del params
        return {}

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        params = self._validated(raw)
        self._level(node_id)
        names, size = await self._doomed(params)
        items = listed(names)
        if size:
            items.append(say("About {size} freed", size=size_text(size)))
        items.append(
            say("Anything that becomes unused before you press Prune goes as well")
        )
        return ActionPreview(
            summary=say("{count} will be removed", count=len(names)),
            items=items,
            blocked=not names,
        )

    async def run(self, node_id: str | None, params: P) -> ActionResult:
        self._level(node_id)
        filters = self._filters(params)
        _, answer = await self._session.send(
            "POST",
            f"/{self.kind}/prune",
            {"filters": json.dumps(filters)} if filters else None,
            expected=(200,),
            seconds=300,
        )
        answer = answer if isinstance(answer, dict) else {}
        gone = next(
            (value for key, value in answer.items() if key.endswith("Deleted") and isinstance(value, list)),
            [],
        )
        freed = answer.get("SpaceReclaimed")
        message = (
            say("{count} removed, {size} freed", count=len(gone), size=size_text(freed))
            if isinstance(freed, int) and freed > 0
            else say("{count} removed", count=len(gone))
        )
        return ActionResult(message=message, reload_node_ids=[self.group])


class PruneContainers(_Prune[NoParams]):
    name: ClassVar[str] = "docker_prune_containers"
    title: ClassVar[str] = N_("Prune stopped containers")
    params_model = NoParams
    group = "containers"
    kind = "containers"

    async def _doomed(self, params: NoParams) -> tuple[list[str], int | None]:
        containers = (await read_containers(self._session)).items
        return sorted(
            name_of(one) for one in containers if one.get("State") in {"exited", "created", "dead"}
        ), None


class PruneImages(_Prune[PruneImagesParams]):
    name: ClassVar[str] = "docker_prune_images"
    title: ClassVar[str] = N_("Prune images")
    params_model = PruneImagesParams
    group = "images"
    kind = "images"

    def _filters(self, params: PruneImagesParams) -> dict[str, list[str]]:
        # Without it the daemon prunes only dangling (untagged) images.
        return {"dangling": ["false"]} if params.all_unused else {}

    async def _doomed(self, params: PruneImagesParams) -> tuple[list[str], int | None]:
        containers = (await read_containers(self._session)).items
        images = (await read_images(self._session)).items
        unused = [one for one in images if not users_of_image(containers, str(one.get("Id")))]
        if not params.all_unused:
            unused = [
                one
                for one in unused
                if not [tag for tag in one.get("RepoTags") or [] if tag != "<none>:<none>"]
            ]
        size = sum(one["Size"] for one in unused if isinstance(one.get("Size"), int))
        return sorted(image_title(one) for one in unused), size


class PruneVolumes(_Prune[PruneVolumesParams]):
    name: ClassVar[str] = "docker_prune_volumes"
    title: ClassVar[str] = N_("Prune unused volumes")
    params_model = PruneVolumesParams
    group = "volumes"
    kind = "volumes"

    def _all_by_default(self) -> bool:
        """Before API 1.42 a prune removes named volumes too, and says no other way."""
        version = self._session.version
        return version is not None and version < (1, 42)

    def _filters(self, params: PruneVolumesParams) -> dict[str, list[str]]:
        return {"all": ["true"]} if params.named_too and not self._all_by_default() else {}

    async def _doomed(self, params: PruneVolumesParams) -> tuple[list[str], int | None]:
        containers = (await read_containers(self._session)).items
        volumes = (await read_volumes(self._session)).items
        unused = [one for one in volumes if not users_of_volume(containers, str(one.get("Name")))]
        if not (params.named_too or self._all_by_default()):
            unused = [one for one in unused if ANONYMOUS_VOLUME in labels_of(one)]
        return sorted(str(one.get("Name")) for one in unused), None


class PruneNetworks(_Prune[NoParams]):
    name: ClassVar[str] = "docker_prune_networks"
    title: ClassVar[str] = N_("Prune unused networks")
    params_model = NoParams
    group = "networks"
    kind = "networks"

    async def _doomed(self, params: NoParams) -> tuple[list[str], int | None]:
        containers = (await read_containers(self._session)).items
        networks = (await read_networks(self._session)).items
        return sorted(
            str(one.get("Name"))
            for one in networks
            if str(one.get("Name")) not in BUILT_IN_NETWORKS
            and not users_of_network(containers, one)
        ), None


# --- making a volume or a network (D411) -----------------------------------------


class NewVolume(JsonAction[NewVolumeParams]):
    name: ClassVar[str] = "docker_new_volume"
    title: ClassVar[str] = N_("New volume")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "level"
    requires: ClassVar[Access] = "structure"
    params_model = NewVolumeParams

    def __init__(self, session: DockerSession) -> None:
        self._session = session

    async def run(self, node_id: str | None, params: NewVolumeParams) -> ActionResult:
        if node_id != "volumes":
            raise ActionRefused("not_applicable", say("Make a volume from Volumes"))
        # Creating a volume of a taken name answers 201 and changes nothing.
        volumes = (await read_volumes(self._session)).items
        if any(one.get("Name") == params.name for one in volumes):
            raise ActionRefused("conflict", say("A volume of that name exists already"))
        await self._session.send(
            "POST", "/volumes/create", body={"Name": params.name, "Driver": "local"}, expected=(201,)
        )
        return ActionResult(
            message=say("{name} created", name=params.name),
            reload_node_ids=["volumes"],
            created_node_id=leaf_id("volume", params.name),
        )


class NewNetwork(JsonAction[NewNetworkParams]):
    name: ClassVar[str] = "docker_new_network"
    title: ClassVar[str] = N_("New network")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "level"
    requires: ClassVar[Access] = "structure"
    params_model = NewNetworkParams

    def __init__(self, session: DockerSession) -> None:
        self._session = session

    async def run(self, node_id: str | None, params: NewNetworkParams) -> ActionResult:
        if node_id != "networks":
            raise ActionRefused("not_applicable", say("Make a network from Networks"))
        status, answer = await self._session.send(
            "POST",
            "/networks/create",
            body={"Name": params.name, "Driver": "bridge", "Internal": params.internal},
            expected=(201, 409),
        )
        if status == 409:
            raise ActionRefused("conflict", say("A network of that name exists already"))
        made = str(answer.get("Id")) if isinstance(answer, dict) else ""
        return ActionResult(
            message=say("{name} created", name=params.name),
            reload_node_ids=["networks"],
            created_node_id=leaf_id("network", made) if made else None,
        )


LIFECYCLE: tuple[type[_Lifecycle[Any]], ...] = (
    StartContainers,
    StopContainers,
    RestartContainers,
    PauseContainers,
    UnpauseContainers,
    KillContainers,
)
REMOVALS: dict[str, type[_Removal[Any]]] = {
    "container": RemoveContainer,
    "image": RemoveImage,
    "volume": RemoveVolume,
    "network": RemoveNetwork,
}
LEVEL_ACTIONS: dict[str, tuple[type[_Prune[Any] | NewVolume | NewNetwork], ...]] = {
    "containers": (PruneContainers,),
    "images": (PruneImages,),
    "volumes": (NewVolume, PruneVolumes),
    "networks": (NewNetwork, PruneNetworks),
}


def plain_actions(session: DockerSession) -> list[Action[Any]]:
    """Every action of this module, built once per adapter."""
    built: list[Action[Any]] = [kind(session) for kind in LIFECYCLE]
    built += [kind(session) for kind in REMOVALS.values()]
    built += [kind(session) for kinds in LEVEL_ACTIONS.values() for kind in kinds]
    return built
