"""The requests this application makes of a container runtime (D82).

Every one of them is asserted against a transport that answers instead of a
daemon, so what is checked is the request itself: the body a container is
created from, the fact that nothing on the host is ever mounted, and that a
daemon's own words never come back out.
"""

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.core.config import settings
from app.services.docker import RESTART_POLICY, DockerEngine
from app.services.engine import EngineError, EngineUnavailable
from app.services.plan import Placement, build_plan
from app.services.templates import template_for


def _spec(published_port: int | None = None, network: str | None = None) -> Any:
    return build_plan(
        template_for("postgres"),
        service_id=uuid4(),
        owner_id=uuid4(),
        placement=Placement(network=network, published_port=published_port),
    ).container


def _engine(handler: Any) -> DockerEngine:
    return DockerEngine("/nowhere.sock", transport=httpx.MockTransport(handler))


def _recorder(status: int = 204, body: Any = None) -> tuple[list[httpx.Request], Any]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body if body is not None else {})

    return seen, handler


async def test_availability_answers_with_the_version_it_found() -> None:
    _, handler = _recorder(200, {"Version": "27.3.1"})

    found = await _engine(handler).availability()

    assert found.available is True
    assert found.version == "27.3.1"
    assert found.reason is None


async def test_a_runtime_that_cannot_be_reached_is_an_answer_not_a_failure() -> None:
    """Asked while a person waits for a page: it says no rather than raising."""

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("No such file or directory: /var/run/docker.sock")

    found = await _engine(handler).availability()

    assert found.available is False
    assert found.reason == "This server cannot reach a container runtime"
    # Not the daemon's words: they name the socket path of this machine.
    assert "docker.sock" not in (found.reason or "")


async def test_something_that_is_not_a_runtime_is_not_taken_for_one() -> None:
    _, handler = _recorder(404, {"message": "page not found"})

    found = await _engine(handler).availability()

    assert found.available is False
    assert found.reason == "The container runtime did not answer as one"


async def test_creating_makes_the_volume_first_and_then_the_container() -> None:
    """A container created with a mount for a volume nobody made would have
    one made for it with the daemon's defaults, and this application would not
    recognise it later."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"Id": "abc"})

    spec = _spec()
    await _engine(handler).create(spec)

    assert [request.url.path for request in seen] == [
        "/volumes/create",
        "/containers/create",
    ]
    volume = json.loads(seen[0].content)
    assert volume["Name"] == spec.volume
    assert volume["Labels"] == dict(spec.labels)
    assert seen[1].url.params["name"] == spec.name


async def test_the_container_is_created_from_the_specification_and_nothing_else() -> (
    None
):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"Id": "abc"})

    spec = _spec(published_port=15432, network="dataplayer_default")
    await _engine(handler).create(spec)

    body = json.loads(seen[1].content)
    assert body["Image"] == spec.image
    assert body["Labels"] == dict(spec.labels)
    assert body["ExposedPorts"] == {"5432/tcp": {}}
    assert sorted(body["Env"]) == sorted(
        f"{key}={value}" for key, value in spec.environment.items()
    )
    assert body["NetworkingConfig"] == {
        "EndpointsConfig": {"dataplayer_default": {}}
    }
    assert body["HostConfig"]["RestartPolicy"] == {"Name": RESTART_POLICY}


async def test_the_only_mount_is_the_service_s_own_named_volume() -> None:
    """A bind mount is how the old application let a request reach the host."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"Id": "abc"})

    spec = _spec()
    await _engine(handler).create(spec)

    host_config = json.loads(seen[1].content)["HostConfig"]
    assert host_config["Mounts"] == [
        {"Type": "volume", "Source": spec.volume, "Target": spec.data_path}
    ]
    assert "Binds" not in host_config


async def test_a_published_port_is_bound_to_this_machine_only() -> None:
    """A database somebody asked this server to start is not one they asked it
    to publish to the network."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"Id": "abc"})

    await _engine(handler).create(_spec(published_port=15432))

    bindings = json.loads(seen[1].content)["HostConfig"]["PortBindings"]
    assert bindings == {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "15432"}]}


async def test_a_service_that_is_not_published_binds_no_port() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"Id": "abc"})

    await _engine(handler).create(_spec())

    assert "PortBindings" not in json.loads(seen[1].content)["HostConfig"]


@pytest.mark.parametrize(
    ("verb", "path"),
    [("start", "start"), ("stop", "stop"), ("restart", "restart")],
)
async def test_the_lifecycle_verbs_name_the_container(verb: str, path: str) -> None:
    seen, handler = _recorder(204)

    await getattr(_engine(handler), verb)("dataplayer-svc-postgres-abc")

    assert seen[0].url.path == f"/containers/dataplayer-svc-postgres-abc/{path}"
    assert seen[0].method == "POST"


async def test_starting_something_already_started_is_what_was_asked_for() -> None:
    seen, handler = _recorder(304)

    await _engine(handler).start("whatever")

    assert len(seen) == 1


def _ours(state: str = "running") -> Any:
    """A daemon holding one container this application made."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/json"):
            return httpx.Response(
                200,
                json={
                    "State": {"Running": state == "running"},
                    "Config": {"Labels": {"dataplayer.service": "abc"}},
                },
            )
        return httpx.Response(204)

    return seen, handler


async def test_removal_takes_the_container_and_then_its_volume() -> None:
    seen, handler = _ours()

    await _engine(handler).remove("container", volume="volume")

    assert [(r.method, r.url.path) for r in seen] == [
        ("GET", "/containers/container/json"),
        ("DELETE", "/containers/container"),
        ("DELETE", "/volumes/volume"),
    ]
    assert seen[1].url.params["force"] == "true"


async def test_removing_what_is_already_gone_is_success() -> None:
    """Removal's goal is a state, so retrying a half-finished one must not be
    told off for the half that worked."""
    _, handler = _recorder(404, {"message": "No such container"})

    await _engine(handler).remove("container", volume="volume")


async def test_the_volume_is_kept_when_removal_is_not_asked_to_take_it() -> None:
    seen, handler = _ours()

    await _engine(handler).remove("container", volume=None)

    assert [request.url.path for request in seen] == [
        "/containers/container/json",
        "/containers/container",
    ]


async def test_a_container_this_application_did_not_make_is_not_removed() -> None:
    """Names are predictable — template plus a service id — so one of that
    name that carries no label of ours is somebody else's (D86)."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/json"):
            return httpx.Response(
                200, json={"State": {"Running": True}, "Config": {"Labels": {}}}
            )
        return httpx.Response(204)

    with pytest.raises(EngineError, match="not made by this application"):
        await _engine(handler).remove("dataplayer-svc-postgres-abc", volume="v")

    assert [request.method for request in seen] == ["GET"]


async def test_a_container_is_created_with_what_it_may_take_of_the_machine() -> None:
    """A container with no limits can take all of it, and a person starting a
    database is not asking for that (D86)."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"Id": "abc"})

    await _engine(handler).create(_spec())

    host_config = json.loads(seen[1].content)["HostConfig"]
    assert host_config["Memory"] == settings.SERVICE_MEMORY_MB * 1024 * 1024
    assert host_config["NanoCpus"] == int(settings.SERVICE_CPUS * 1_000_000_000)
    assert host_config["PidsLimit"] == settings.SERVICE_PIDS_LIMIT


async def test_a_refusal_says_what_happened_and_not_where() -> None:
    """The daemon's message names images and directories of the host; it goes
    to the log, and this repository's own sentence goes to the caller."""
    _, handler = _recorder(
        409, {"message": 'Conflict. The container name "/x" is already in use'}
    )

    with pytest.raises(EngineError) as refused:
        await _engine(handler).start("x")

    assert "already in use" not in str(refused.value)
    assert str(refused.value) == "It is busy, or something with that name already exists"


async def test_a_daemon_that_goes_away_mid_command_is_unavailable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(EngineUnavailable):
        await _engine(handler).stop("x")


async def test_a_pull_asks_for_the_exact_image_and_tag() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text='{"status":"Pulling from library/postgres"}\n')

    await _engine(handler).pull("postgres:18")

    assert seen[0].url.path == "/images/create"
    assert seen[0].url.params["fromImage"] == "postgres"
    assert seen[0].url.params["tag"] == "18"


async def test_a_pull_that_fails_inside_a_successful_answer_is_a_failure() -> None:
    """The daemon answers 200 and then streams what went wrong."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '{"status":"Pulling from library/postgres"}\n'
                '{"errorDetail":{"message":"manifest unknown"},"error":"manifest unknown"}\n'
            ),
        )

    with pytest.raises(EngineError, match="could not be fetched"):
        await _engine(handler).pull("postgres:18")
