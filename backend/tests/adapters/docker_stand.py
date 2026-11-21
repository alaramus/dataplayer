"""The Docker daemon behind SSH the Docker source tests run against (D405).

Needs `docker compose up -d docker-remote`. What the tests read is made through
the same forwarded socket — a Compose-labelled container on a network of its
own with a volume, one with a TTY, one that failed — so the stand needs
nothing prepared by hand.
"""

import uuid
from pathlib import Path
from urllib.parse import urlsplit

from app.adapters.docker.options import DockerOptions
from app.adapters.docker.session import DockerSession
from app.adapters.docker_api.client import EngineClient
from app.adapters.registry import AdapterContext
from app.adapters.ssh.adapter import SshAdapter
from app.adapters.ssh.options import SshPassword
from tests.utils import services
from tests.utils.ssh import pinned_key

THROUGH = str(uuid.uuid4())
PROJECT = "dp-test"
IMAGE = "alpine:3.20"


class Through:
    """The stand's SSH server, as the owner's SSH connection."""

    def __init__(self, ssh: SshAdapter) -> None:
        self._ssh = ssh

    async def endpoint(self, connection_id: uuid.UUID, host: str, port: int) -> tuple[str, int]:
        raise AssertionError("a Docker source forwards a socket, not a port")

    async def socket_endpoint(self, connection_id: uuid.UUID, path: str) -> tuple[str, int]:
        assert str(connection_id) == THROUGH
        return await self._ssh.forward_socket(path)


async def open_through() -> Through:
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
    return Through(SshAdapter(options, AdapterContext(home_dir=Path("."))))


def options(socket: str = "/var/run/docker.sock") -> DockerOptions:
    return DockerOptions(ssh_connection=THROUGH, socket=socket)


async def make(engine: EngineClient, name: str, body: dict[str, object]) -> str:
    """A container by name, made once and found again on later runs, started:
    a stand restarted stops every container it held."""
    found = await engine.request(
        "GET", f"/containers/{name}/json", expected=(200, 404)
    )
    if found.status == 200:
        container = str(found.json()["Id"])
    else:
        made = await engine.request(
            "POST", "/containers/create", params={"name": name}, json=body, expected=(201,)
        )
        container = str(made.json()["Id"])
    await engine.request("POST", f"/containers/{container}/start", expected=(204, 304))
    return container


async def build_stand(through: Through) -> dict[str, str]:
    """What the tests read, made through the forwarded socket."""
    engine = await DockerSession(options(), through).engine()
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
    web = await make(
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
    tty = await make(
        engine,
        "dp-test-tty",
        {"Image": IMAGE, "Tty": True, "Cmd": ["sh", "-c", "echo hello tty; sleep 100000"]},
    )
    failed = await make(engine, "dp-test-failed", {"Image": IMAGE, "Cmd": ["sh", "-c", "exit 3"]})
    await engine.request("POST", f"/containers/{failed}/wait", expected=(200,), seconds=30)
    return {"web": web, "tty": tty, "failed": failed}
