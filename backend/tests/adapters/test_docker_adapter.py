"""A Docker daemon read through an SSH server (D405–D408).

Needs `docker compose up -d docker-remote`: dockerd and sshd in one
container, the daemon's socket forwarded over SSH. The fixture makes what it
reads through the same forwarded socket — a Compose-labelled container on a
network of its own with a volume, one with a TTY, one that failed — so the
stand needs nothing prepared by hand.
"""

import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.adapters.catalog import ImageNode, NetworkNode
from app.adapters.content import ContentRequest, JsonContent, JsonObject
from app.adapters.docker.adapter import DockerAdapter
from app.adapters.docker.options import DockerOptions
from app.adapters.docker.session import DockerSession
from app.adapters.docker_api.client import EngineClient
from app.adapters.fetch import FetchRequest, ScalarFilter
from app.adapters.protocol import NodeNotFound
from app.adapters.registry import AdapterContext
from app.adapters.ssh.adapter import SshAdapter
from app.adapters.ssh.options import SshPassword
from tests.utils import services
from tests.utils.ssh import pinned_key

THROUGH = str(uuid.uuid4())
PROJECT = "dp-test"
IMAGE = "alpine:3.20"


class _Through:
    """The stand's SSH server, as the owner's SSH connection."""

    def __init__(self, ssh: SshAdapter) -> None:
        self._ssh = ssh

    async def endpoint(self, connection_id: uuid.UUID, host: str, port: int) -> tuple[str, int]:
        raise AssertionError("a Docker source forwards a socket, not a port")

    async def socket_endpoint(self, connection_id: uuid.UUID, path: str) -> tuple[str, int]:
        assert str(connection_id) == THROUGH
        return await self._ssh.forward_socket(path)


@pytest.fixture(scope="module")
async def through() -> _Through:
    parts = urlsplit(services.DOCKER_REMOTE.require())
    host, port = str(parts.hostname), parts.port or 22
    options = SshPassword.model_validate(
        {
            "auth_method": "password",
            "host": host,
            "port": port,
            "username": parts.username,
            "password": parts.password,
            "host_key": await pinned_key(host, port),
        }
    )
    return _Through(SshAdapter(options, AdapterContext(home_dir=Path("."))))


def _options(socket: str = "/var/run/docker.sock") -> DockerOptions:
    return DockerOptions(ssh_connection=THROUGH, socket=socket)


async def _make(engine: EngineClient, name: str, body: dict[str, object]) -> str:
    """A container by name, made once and found again on later runs."""
    found = await engine.request(
        "GET", f"/containers/{name}/json", expected=(200, 404)
    )
    if found.status == 200:
        return str(found.json()["Id"])
    made = await engine.request(
        "POST", "/containers/create", params={"name": name}, json=body, expected=(201,)
    )
    container = str(made.json()["Id"])
    await engine.request("POST", f"/containers/{container}/start", expected=(204, 304))
    return container


@pytest.fixture(scope="module")
async def stand(through: _Through) -> dict[str, str]:
    """What the tests read, made through the forwarded socket."""
    engine = await DockerSession(_options(), through).engine()
    repository, _, tag = IMAGE.partition(":")
    await engine.request(
        "POST",
        "/images/create",
        params={"fromImage": repository, "tag": tag},
        expected=(200,),
        seconds=300,
    )
    await engine.request("POST", "/volumes/create", json={"Name": "dp-test-data"}, expected=(201,))
    networks = await engine.request(
        "GET", "/networks", params={"filters": '{"name":["dp-test-net"]}'}, expected=(200,)
    )
    if not [one for one in networks.json() if one["Name"] == "dp-test-net"]:
        await engine.request(
            "POST",
            "/networks/create",
            json={"Name": "dp-test-net", "Labels": {"com.docker.compose.network": "net"}},
            expected=(201,),
        )
    web = await _make(
        engine,
        "dp-test-web",
        {
            "Image": IMAGE,
            "Cmd": ["sh", "-c", "echo started; echo warned >&2; sleep 100000"],
            "Labels": {
                "com.docker.compose.project": PROJECT,
                "com.docker.compose.service": "web",
            },
            "HostConfig": {
                "Mounts": [{"Type": "volume", "Source": "dp-test-data", "Target": "/data"}],
                "NetworkMode": "dp-test-net",
            },
        },
    )
    tty = await _make(
        engine,
        "dp-test-tty",
        {"Image": IMAGE, "Tty": True, "Cmd": ["sh", "-c", "echo hello tty; sleep 100000"]},
    )
    failed = await _make(engine, "dp-test-failed", {"Image": IMAGE, "Cmd": ["sh", "-c", "exit 3"]})
    await engine.request("POST", f"/containers/{failed}/wait", expected=(200,), seconds=30)
    return {"web": web, "tty": tty, "failed": failed}


@pytest.fixture
def adapter(through: _Through) -> DockerAdapter:
    return DockerAdapter(_options(), through)


async def test_the_check_names_the_api_spoken(adapter: DockerAdapter) -> None:
    checked = await adapter.check_connection()
    assert checked.ok, checked.message
    assert "1.4" in checked.message


async def test_a_socket_that_is_not_there_is_one_sentence(through: _Through) -> None:
    checked = await DockerAdapter(_options("/var/run/nothing.sock"), through).check_connection()
    assert not checked.ok
    assert "/var/run/nothing.sock" in checked.message
    assert "AllowStreamLocalForwarding" in checked.message


async def test_the_top_is_the_system_section_and_four_groups(adapter: DockerAdapter) -> None:
    top = await adapter.list_children(None)
    assert [node.id for node in top] == ["system", "containers", "images", "volumes", "networks"]


async def test_containers_are_grouped_by_compose_project(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    projects = await adapter.list_children("containers")
    ids = [node.id for node in projects]
    assert f"project:{PROJECT}" in ids
    assert ids[-1] == "standalone"
    [web] = await adapter.list_children(f"project:{PROJECT}")
    assert web.kind == "container"
    assert web.id == f"container:{stand['web']}"
    assert web.state == "running"
    assert web.service == "web"
    standalone = {node.name: node for node in await adapter.list_children("standalone")}
    assert standalone["dp-test-failed"].state == "failed"  # type: ignore[union-attr] # a container


@pytest.mark.usefixtures("stand")
async def test_a_group_is_a_table_filtered_here(adapter: DockerAdapter) -> None:
    page = await adapter.fetch(
        FetchRequest(
            node_id="containers",
            filters=[ScalarFilter(column="name", op="starts_with", value="dp-test")],
        )
    )
    names = [row[0] for row in page.rows]
    assert sorted(names) == ["dp-test-failed", "dp-test-tty", "dp-test-web"]
    assert page.update_supported is False


async def test_logs_keep_their_stream_and_come_newest_first(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    page = await adapter.fetch(FetchRequest(node_id=f"container:{stand['web']}/logs"))
    assert [row[1:] for row in page.rows] == [["stderr", "warned"], ["stdout", "started"]]
    assert all(row[0] and row[0].endswith("Z") for row in page.rows)
    tty = await adapter.fetch(FetchRequest(node_id=f"container:{stand['tty']}/logs"))
    assert tty.rows[0][1:] == ["stdout", "hello tty"]


async def test_processes_of_a_stopped_container_are_none(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    running = await adapter.fetch(FetchRequest(node_id=f"container:{stand['web']}/processes"))
    assert "PID" in [column.name for column in running.columns]
    assert any("sleep" in (cell or "") for row in running.rows for cell in row)
    stopped = await adapter.fetch(FetchRequest(node_id=f"container:{stand['failed']}/processes"))
    assert stopped.rows == []


@pytest.mark.usefixtures("stand")
async def test_an_image_counts_its_containers_and_shows_its_layers(adapter: DockerAdapter) -> None:
    images = await adapter.list_children("images")
    [alpine] = [node for node in images if isinstance(node, ImageNode) and IMAGE in node.tags]
    assert isinstance(alpine, ImageNode)
    assert alpine.containers >= 3
    history = await adapter.fetch(FetchRequest(node_id=f"{alpine.id}/history"))
    assert any("alpine-minirootfs" in (row[1] or "") for row in history.rows)


@pytest.mark.usefixtures("stand")
async def test_a_volume_and_a_network_name_their_containers(adapter: DockerAdapter) -> None:
    users = await adapter.fetch(FetchRequest(node_id="volume:dp-test-data/containers"))
    assert [row[0] for row in users.rows] == ["dp-test-web"]
    networks = {
        node.name: node
        for node in await adapter.list_children("networks")
        if isinstance(node, NetworkNode)
    }
    assert networks["bridge"].network_kind == "built_in"
    assert networks["dp-test-net"].network_kind == "compose"
    on_it = await adapter.fetch(FetchRequest(node_id=f"{networks['dp-test-net'].id}/containers"))
    assert [row[0] for row in on_it.rows] == ["dp-test-web"]


async def test_inspect_is_the_daemons_json_as_a_tree(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    content = await adapter.read_content(
        ContentRequest(node_id=f"container:{stand['web']}", representation="tree")
    )
    assert isinstance(content, JsonContent)
    assert isinstance(content.value, JsonObject)
    assert "Config" in [entry.name for entry in content.value.entries]


async def test_a_container_holds_its_views(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    views = await adapter.list_children(f"container:{stand['web']}")
    assert [node.id.rsplit("/", 1)[1] for node in views] == ["inspect", "logs", "processes"]
    assert views[0].representations[0].kind == "tree"
    content = await adapter.read_content(
        ContentRequest(node_id=views[0].id, representation="tree")
    )
    assert isinstance(content, JsonContent)


async def test_a_path_leads_through_the_project(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    path = await adapter.path_to(f"container:{stand['web']}/logs")
    assert [node.id for node in path] == [
        "containers",
        f"project:{PROJECT}",
        f"container:{stand['web']}",
        f"container:{stand['web']}/logs",
    ]


async def test_a_container_that_is_gone_is_not_found(adapter: DockerAdapter) -> None:
    with pytest.raises(NodeNotFound):
        await adapter.list_children("container:" + "0" * 64)


@pytest.mark.usefixtures("stand")
async def test_the_system_reports_read_like_tables(adapter: DockerAdapter) -> None:
    engine = await adapter.fetch(FetchRequest(node_id="system/engine"))
    settings = {row[0]: row[1] for row in engine.rows}
    assert settings["ApiVersion"]
    disk = await adapter.fetch(FetchRequest(node_id="system/disk"))
    assert "volume" in [row[0] for row in disk.rows]
    events = await adapter.fetch(FetchRequest(node_id="system/events"))
    assert events.rows
