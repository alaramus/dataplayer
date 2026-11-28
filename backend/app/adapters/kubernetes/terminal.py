"""A shell inside a pod's container, as its owner's terminal (D472, on D413).

`pods/{name}/exec` over a WebSocket with `v5.channel.k8s.io` (`v4` where the
server has no v5): every frame starts with its channel — 0 what is typed, 1
and 2 what the program prints, 3 the API server's `Status` when it ends, 4 a
resize as `{"Width", "Height"}`. The program is one of a closed list, as
argv. A shell the image lacks ends at once with a `Status` naming the OCI
runtime's failure (*checked*, k3s 1.33); that is said in a sentence of ours.
"""

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

from app.adapters.actions import Action, ActionRefused, ActsOn, FieldChoice, FieldHints
from app.adapters.catalog import NodeKind
from app.adapters.kubernetes.actions import Kube, Target, read, target_of
from app.adapters.kubernetes.discovery import Resource
from app.adapters.kubernetes.reviews import Asked
from app.adapters.kubernetes.session import Forbidden, segment
from app.adapters.layout import layout
from app.adapters.terminal import Terminal, TerminalSize
from app.core.access import Access
from app.core.translation import N_, say

logger = logging.getLogger(__name__)

PROTOCOLS = ["v5.channel.k8s.io", "v4.channel.k8s.io"]
_STDIN, _STDOUT, _STDERR, _STATUS, _RESIZE = 0, 1, 2, 3, 4
# What the runtime says when the program is not in the image.
_NOT_THERE = ("OCI runtime exec failed", "executable file not found", "no such file or directory")

Shell = Literal["/bin/sh", "/bin/bash", "/bin/ash"]


class PodShellParams(BaseModel):
    container: str = Field(
        default="",
        max_length=63,
        pattern=r"^([a-z0-9]([-a-z0-9]*[a-z0-9])?)?$",
        title=N_("Container"),
        description=N_("Empty for the pod's first container"),
        json_schema_extra=layout(),
    )
    shell: Shell = Field(default="/bin/sh", title=N_("Shell"), json_schema_extra=layout())


def exit_code(status: Any) -> int | None:
    """The code a `Status` from channel 3 carries: 0 on Success, the
    `ExitCode` cause on NonZeroExitCode, None for any other failure."""
    if not isinstance(status, dict):
        return None
    if status.get("status") == "Success":
        return 0
    details = status.get("details")
    for cause in (details.get("causes") if isinstance(details, dict) else None) or []:
        if isinstance(cause, dict) and cause.get("reason") == "ExitCode":
            message = str(cause.get("message") or "")
            return int(message) if message.isdigit() else None
    return None


class ExecTerminal:
    """One exec's socket: channel-tagged frames both ways."""

    def __init__(self, socket: ClientConnection, shell: str) -> None:
        self._socket = socket
        self._shell = shell
        self._code: int | None = None
        self._ended = False
        self._resizes: set[asyncio.Task[None]] = set()

    async def read(self) -> bytes:
        while not self._ended:
            try:
                frame = await self._socket.recv()
            except ConnectionClosed:
                self._ended = True
                return b""
            if isinstance(frame, str):
                frame = frame.encode()
            if not frame:
                continue
            channel, data = frame[0], frame[1:]
            if channel in (_STDOUT, _STDERR):
                if data:
                    return data
                continue
            if channel == _STATUS and data:
                return self._ending(data)
        return b""

    def _ending(self, data: bytes) -> bytes:
        try:
            status = json.loads(data)
        except ValueError:
            status = None
        self._code = exit_code(status)
        message = str(status.get("message") or "") if isinstance(status, dict) else ""
        if self._code is None and any(word in message for word in _NOT_THERE):
            logger.info("A container has no %s: %s", self._shell, message[:300])
            return (
                say(
                    "There is no {shell} in this container; open the terminal again and choose another shell",
                    shell=self._shell,
                )
                + "\r\n"
            ).encode()
        if self._code is None and message:
            logger.info("A pod's exec ended: %s", message[:300])
        return b""

    async def write(self, data: bytes) -> None:
        await self._send(bytes([_STDIN]) + data)

    def resize(self, size: TerminalSize) -> None:
        frame = bytes([_RESIZE]) + json.dumps({"Width": size.cols, "Height": size.rows}).encode()
        task = asyncio.create_task(self._send(frame))
        self._resizes.add(task)
        task.add_done_callback(self._resizes.discard)

    async def _send(self, frame: bytes) -> None:
        try:
            await self._socket.send(frame)
        except ConnectionClosed:
            return

    async def exit_status(self) -> int | None:
        return self._code

    async def close(self) -> None:
        for task in list(self._resizes):
            task.cancel()
        await self._socket.close()


class PodTerminal(Action[PodShellParams]):
    """Its form opens a terminal in a pod's container rather than running (D472)."""

    name: ClassVar[str] = "kubernetes_terminal"
    title: ClassVar[str] = N_("Terminal")
    icon: ClassVar[str | None] = "terminal"
    in_view: ClassVar[bool] = True
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"k8s_object"})
    acts_on: ClassVar[ActsOn] = "node"
    # Typing into a container is typing into what it can reach (D149).
    requires: ClassVar[Access] = "own"
    params_model = PodShellParams
    keys: ClassVar[frozenset[str]] = frozenset({"/pods"})

    def __init__(self, kube: Kube) -> None:
        self._kube = kube

    def fits(self, resource: Resource) -> bool:
        return resource.key in self.keys

    def asked(self, target: Target) -> Asked:
        return self.asked_at(target.resource, target.namespace)

    def asked_at(self, resource: Resource, namespace: str | None) -> Asked:
        return Asked(verb="create", group="", resource="pods", namespace=namespace, subresource="exec")

    async def field_hints(self, node_id: str | None) -> FieldHints:
        target = await target_of(self._kube, node_id, set(self.keys))
        names = containers(await read(self._kube, target))
        return FieldHints(
            choices={"container": [FieldChoice(value=name, label=name) for name in names]},
            values={"container": names[0]} if names else {},
        )

    async def open_terminal(
        self, node_id: str | None, raw: Mapping[str, Any], size: TerminalSize
    ) -> Terminal:
        params = self._validated(raw)
        target = await target_of(self._kube, node_id, set(self.keys))
        body = await read(self._kube, target)
        if (body.get("status") or {}).get("phase") != "Running":
            raise ActionRefused("not_applicable", say("The pod is not running, so nothing runs in it"))
        names = containers(body)
        container = params.container or (names[0] if names else "")
        if container not in names:
            raise ActionRefused("not_applicable", say("The pod has no container {name}", name=container))
        socket = await self._kube.session.socket(
            f"/api/v1/namespaces/{segment(target.namespace or '')}/pods/{segment(target.name)}/exec",
            [
                ("container", container),
                ("command", params.shell),
                ("stdin", "true"),
                ("stdout", "true"),
                ("stderr", "true"),
                ("tty", "true"),
            ],
            PROTOCOLS,
            asked=Forbidden("create", "pods/exec"),
            node_id=target.node_id,
        )
        terminal = ExecTerminal(socket, params.shell)
        terminal.resize(size)
        return terminal


def containers(pod: dict[str, Any]) -> list[str]:
    """A pod's containers by name, as its spec lists them; init containers
    have ended by the time anybody types."""
    listed = (pod.get("spec") or {}).get("containers") or []
    return [str(one.get("name")) for one in listed if isinstance(one, dict) and one.get("name")]
