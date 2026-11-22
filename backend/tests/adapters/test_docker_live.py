"""A terminal inside a container, and what changed told as it happens (D413, D414).

Needs `docker compose up -d docker-remote`.
"""

import asyncio
from collections.abc import Callable

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.changes import Changed
from app.adapters.docker.adapter import DockerAdapter
from app.adapters.docker.session import DockerSession
from app.adapters.docker.watch import changed_by, views_told
from app.adapters.docker_api.client import EngineClient
from app.adapters.terminal import OpensTerminal, Terminal, TerminalSize
from tests.adapters.docker_stand import (
    IMAGE,
    Through,
    build_stand,
    make,
    open_through,
    options,
)

SIZE = TerminalSize(cols=100, rows=30)


class _Told:
    """A sink that remembers what it was told and wakes whoever waits for it."""

    def __init__(self, wanted: Callable[[Changed], bool]) -> None:
        self.told: list[Changed] = []
        self.arrived = asyncio.Event()
        self._wanted = wanted

    def __call__(self, changed: Changed) -> None:
        self.told.append(changed)
        if self._wanted(changed):
            self.arrived.set()


@pytest.fixture(scope="module")
async def through() -> Through:
    return await open_through()


@pytest.fixture(scope="module")
async def stand(through: Through) -> dict[str, str]:
    return await build_stand(through)


@pytest.fixture
def adapter(through: Through) -> DockerAdapter:
    return DockerAdapter(options(), through)


@pytest.fixture
async def engine(through: Through, stand: dict[str, str]) -> EngineClient:
    del stand
    return await DockerSession(options(), through).engine()


def _opener(adapter: DockerAdapter) -> OpensTerminal:
    action = adapter.action("docker_terminal")
    assert isinstance(action, OpensTerminal)
    return action


async def _all_of(terminal: Terminal) -> bytes:
    out = b""
    async with asyncio.timeout(10):
        while chunk := await terminal.read():
            out += chunk
    return out


async def test_a_shell_runs_inside_the_container(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    terminal = await _opener(adapter).open_terminal(
        f"container:{stand['web']}", {"shell": "/bin/sh"}, SIZE
    )
    try:
        await terminal.write(b"echo $((6*7)); whoami; exit 3\n")
        out = await _all_of(terminal)
        assert b"42" in out
        assert await terminal.exit_status() == 3
    finally:
        await terminal.close()


async def test_a_shell_the_image_lacks_is_said_in_our_words(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    terminal = await _opener(adapter).open_terminal(
        f"container:{stand['web']}", {"shell": "/bin/bash"}, SIZE
    )
    try:
        out = await _all_of(terminal)
        assert b"/bin/bash" in out
        assert b"OCI runtime" not in out
    finally:
        await terminal.close()


async def test_a_stopped_container_has_no_terminal(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    with pytest.raises(ActionRefused):
        await _opener(adapter).open_terminal(f"container:{stand['failed']}", {}, SIZE)


async def test_the_terminal_is_offered_on_a_container_alone(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    offered = {one.name for one in await adapter.available(f"container:{stand['web']}")}
    assert "docker_terminal" in offered
    assert "docker_terminal" not in {one.name for one in await adapter.available("project:dp-test")}
    assert adapter.action("docker_terminal").requires == "own"


async def test_a_followed_log_tells_its_tab_when_lines_arrive(
    adapter: DockerAdapter, engine: EngineClient
) -> None:
    await engine.request("DELETE", "/containers/dp-test-ticker", params={"force": "true"}, expected=(204, 404))
    ticker = await make(
        engine,
        "dp-test-ticker",
        {"Image": IMAGE, "Cmd": ["sh", "-c", "while true; do echo tick; sleep 0.3; done"]},
    )
    sink = _Told(lambda _: True)
    watch = await adapter.watch_changes(sink)
    try:
        await watch.follow([f"container:{ticker}/logs"])
        async with asyncio.timeout(10):
            await sink.arrived.wait()
        await asyncio.sleep(1.0)
        # Many lines, few tellings: at most one every two seconds.
        assert len(sink.told) <= 2
        assert sink.told[0].nodes == {f"container:{ticker}/logs"}
    finally:
        await watch.close()
        await engine.request("DELETE", f"/containers/{ticker}", params={"force": "true"}, expected=(204,))


async def test_an_event_tells_the_level_it_changes(
    adapter: DockerAdapter, engine: EngineClient
) -> None:
    sink = _Told(lambda changed: "images" in changed.levels)
    watch = await adapter.watch_changes(sink)
    try:
        await watch.follow(["images", "containers"])
        await asyncio.sleep(1.0)
        await engine.request(
            "POST", f"/images/{IMAGE}/tag", params={"repo": "dp-test/tagged", "tag": "x"}, expected=(201,)
        )
        async with asyncio.timeout(10):
            await sink.arrived.wait()
    finally:
        await watch.close()
        await engine.request("DELETE", "/images/dp-test/tagged:x", expected=(200, 404))


def test_an_event_names_only_the_levels_shown() -> None:
    started = {
        "Type": "container",
        "Action": "start",
        "Actor": {"Attributes": {"com.docker.compose.project": "shop"}},
    }
    assert changed_by(started, frozenset({"containers", "project:shop", "images"})) == Changed(
        levels=frozenset({"containers", "project:shop"})
    )
    assert changed_by(started, frozenset({"images"})) is None
    exec_start = {"Type": "container", "Action": "exec_start: /bin/sh -c true"}
    assert changed_by(exec_start, frozenset({"containers"})) is None
    healthy = {"Type": "container", "Action": "health_status: healthy", "Actor": {}}
    assert changed_by(healthy, frozenset({"standalone"})) == Changed(levels=frozenset({"standalone"}))


C1 = "a" * 64
C2 = "b" * 64
NET = "c" * 64
IMG = "sha256:" + "d" * 64


def _viewed(*ids: str) -> dict[str, tuple[str, str]]:
    return {one: (one.split(":", 1)[0], one.split(":", 1)[1].removesuffix("/inspect")) for one in ids}


def test_a_container_event_tells_its_own_view_and_the_lists_of_users() -> None:
    """Its own view by id; an image's and a volume's list states, so every one (D422)."""
    viewed = _viewed(
        f"container:{C1}/inspect", f"container:{C2}", f"image:{IMG}", "volume:data", f"network:{NET}"
    )
    paused = {"Type": "container", "Action": "pause", "Actor": {"ID": C1}}
    assert views_told(paused, viewed) == {f"container:{C1}/inspect", f"image:{IMG}", "volume:data"}
    healthy = {"Type": "container", "Action": "health_status: healthy", "Actor": {"ID": C2}}
    assert f"container:{C2}" in views_told(healthy, viewed)
    exec_start = {"Type": "container", "Action": "exec_start: /bin/sh -c true", "Actor": {"ID": C1}}
    assert views_told(exec_start, viewed) == frozenset()


def test_a_network_event_tells_the_network_and_the_container_it_connects() -> None:
    viewed = _viewed(f"container:{C1}/inspect", f"network:{NET}", f"image:{IMG}")
    connected = {
        "Type": "network",
        "Action": "connect",
        "Actor": {"ID": NET, "Attributes": {"container": C1}},
    }
    assert views_told(connected, viewed) == {f"container:{C1}/inspect", f"network:{NET}"}


def test_a_pull_tells_every_image_view_and_a_tag_its_own() -> None:
    other = "sha256:" + "e" * 64
    viewed = _viewed(f"image:{IMG}", f"image:{other}")
    pulled = {"Type": "image", "Action": "pull", "Actor": {"ID": "alpine:3.20"}}
    assert views_told(pulled, viewed) == {f"image:{IMG}", f"image:{other}"}
    tagged = {"Type": "image", "Action": "tag", "Actor": {"ID": IMG}}
    assert views_told(tagged, viewed) == {f"image:{IMG}"}


async def test_an_open_view_is_told_when_its_container_changes(
    adapter: DockerAdapter, engine: EngineClient, stand: dict[str, str]
) -> None:
    node = f"container:{stand['tty']}/inspect"
    sink = _Told(lambda changed: node in changed.nodes)
    watch = await adapter.watch_changes(sink)
    try:
        # A view alone, no level: the events stream opens for it too.
        await watch.follow([node])
        await asyncio.sleep(1.0)
        await engine.request("POST", f"/containers/{stand['tty']}/pause", expected=(204,))
        async with asyncio.timeout(10):
            await sink.arrived.wait()
    finally:
        await watch.close()
        await engine.request("POST", f"/containers/{stand['tty']}/unpause", expected=(204, 409, 500))
