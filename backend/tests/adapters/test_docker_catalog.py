"""The Docker source without a daemon: answers recorded from the stand (D405–D409)."""

import uuid

import httpx
import pytest
from pydantic import ValidationError

from app.adapters.catalog import ImageNode
from app.adapters.docker.adapter import DockerAdapter
from app.adapters.docker.catalog import parse
from app.adapters.docker.inventory import network_kind, ports_of, state_of
from app.adapters.docker.options import DockerOptions
from app.adapters.docker.session import spoken
from app.adapters.docker.tables import log_rows
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import AdapterError, NodeNotFound

THROUGH = str(uuid.uuid4())
HEX = "a" * 64


class _Loopback:
    """A tunnel that is never dialled: the transport answers instead."""

    async def endpoint(self, connection_id: uuid.UUID, host: str, port: int) -> tuple[str, int]:
        raise AssertionError("not a port")

    async def socket_endpoint(self, connection_id: uuid.UUID, path: str) -> tuple[str, int]:
        return "127.0.0.1", 1


def _adapter(answers: dict[str, httpx.Response], api: str = "1.57") -> DockerAdapter:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/_ping":
            return httpx.Response(200, text="OK")
        if request.url.path == "/version":
            return httpx.Response(200, json={"ApiVersion": api, "Version": "29.10.0"})
        for path, answer in answers.items():
            if request.url.path.endswith(path):
                return answer
        return httpx.Response(404, json={"message": "no such thing at /var/lib/docker"})

    adapter = DockerAdapter(
        DockerOptions(ssh_connection=THROUGH),
        _Loopback(),
        httpx.MockTransport(handler),
    )
    adapter.seen = seen  # type: ignore[attr-defined] # the test reads what was asked
    return adapter


@pytest.mark.parametrize(
    ("state", "status", "word"),
    [
        ("running", "Up 2 minutes", "running"),
        ("running", "Up 2 minutes (healthy)", "healthy"),
        ("running", "Up 2 minutes (unhealthy)", "unhealthy"),
        ("running", "Up 1 second (health: starting)", "starting"),
        ("exited", "Exited (0) 1 hour ago", "stopped"),
        ("exited", "Exited (3) 1 hour ago", "failed"),
        ("exited", "Exited (137) 1 hour ago", "failed"),
        ("paused", "Up 1 hour (Paused)", "paused"),
        ("restarting", "Restarting (1) 3 seconds ago", "restarting"),
        ("created", "Created", "created"),
        ("dead", "Dead", "dead"),
        ("frozen", "?", "unknown"),
    ],
)
def test_a_state_is_one_word(state: str, status: str, word: str) -> None:
    assert state_of({"State": state, "Status": status}) == word


def test_newer_apis_say_health_in_a_field() -> None:
    assert state_of({"State": "running", "Status": "Up", "Health": {"Status": "unhealthy"}}) == "unhealthy"


def test_a_port_published_on_both_families_is_listed_once() -> None:
    container = {
        "Ports": [
            {"IP": "0.0.0.0", "PrivatePort": 80, "PublicPort": 8080, "Type": "tcp"},
            {"IP": "::", "PrivatePort": 80, "PublicPort": 8080, "Type": "tcp"},
            {"PrivatePort": 443, "Type": "tcp"},
        ]
    }
    assert ports_of(container) == ["8080:80/tcp"]


def test_networks_are_built_in_compose_or_a_users() -> None:
    assert network_kind({"Name": "bridge"}) == "built_in"
    assert network_kind({"Name": "shop_default", "Labels": {"com.docker.compose.network": "default"}}) == "compose"
    assert network_kind({"Name": "mine", "Labels": {}}) == "user"


@pytest.mark.parametrize(
    "node_id",
    [
        "container:abc",
        "container:" + "A" * 64,
        "image:" + HEX,
        "volume:../etc",
        "volume:-starts-badly",
        "network:" + HEX + "/logs",
        "container:" + HEX + "/history",
        "elsewhere:" + HEX,
    ],
)
def test_an_id_not_matching_its_pattern_is_refused(node_id: str) -> None:
    with pytest.raises(ValueError):
        parse(node_id)


def test_ids_name_what_the_daemon_will_not_reuse() -> None:
    assert parse("container:" + HEX + "/logs").view == "logs"
    assert parse("image:sha256:" + HEX).key == "sha256:" + HEX
    assert parse("volume:data_1.v2").key == "data_1.v2"
    assert parse("project:my%2Fapp").project == "my/app"
    assert parse("standalone").project == ""


@pytest.mark.parametrize("socket", ["docker.sock", "/var/../run/docker.sock", "/a\x00b", "/" + "x" * 255])
def test_a_socket_is_an_absolute_plain_path(socket: str) -> None:
    with pytest.raises(ValidationError):
        DockerOptions(ssh_connection=THROUGH, socket=socket)


def test_an_ssh_connection_is_required() -> None:
    with pytest.raises(ValidationError):
        DockerOptions.model_validate({"socket": "/var/run/docker.sock"})
    with pytest.raises(ValidationError):
        DockerOptions(ssh_connection="")


def test_the_version_spoken_is_the_lower_and_never_below_the_floor() -> None:
    assert spoken((1, 57)) == (1, 47)
    assert spoken((1, 43)) == (1, 43)
    assert spoken((1, 41)) == (1, 41)
    with pytest.raises(AdapterError) as refused:
        spoken((1, 40))
    assert "1.40" in refused.value.message


async def test_every_request_carries_the_negotiated_version() -> None:
    adapter = _adapter({"/containers/json": httpx.Response(200, json=[])}, api="1.44")
    await adapter.list_children("containers")
    assert "/v1.44/containers/json" in adapter.seen  # type: ignore[attr-defined]


async def test_an_old_daemon_is_refused_by_name() -> None:
    checked = await _adapter({}, api="1.39").check_connection()
    assert not checked.ok
    assert "1.39" in checked.message


async def test_a_proxy_refusing_is_said_apart_from_the_socket() -> None:
    adapter = _adapter({"/containers/json": httpx.Response(403, json={"message": "authz: /secret"})})
    with pytest.raises(AdapterError) as refused:
        await adapter.list_children("containers")
    assert refused.value.error_kind == "auth"
    assert "did not allow" in refused.value.message
    assert "secret" not in refused.value.message


async def test_a_gone_node_is_not_found() -> None:
    adapter = _adapter({})
    with pytest.raises(NodeNotFound):
        await adapter.list_children("container:" + HEX)


async def test_a_stopped_containers_processes_are_none() -> None:
    adapter = _adapter(
        {"/top": httpx.Response(409, json={"message": "container is not running"})}
    )
    page = await adapter.fetch(FetchRequest(node_id=f"container:{HEX}/processes"))
    assert page.rows == []
    assert page.update_reason and "not running" in page.update_reason


async def test_images_count_their_containers_from_the_containers() -> None:
    image = "sha256:" + HEX
    adapter = _adapter(
        {
            "/containers/json": httpx.Response(
                200,
                json=[
                    {"Id": "1" * 64, "Names": ["/a"], "ImageID": image, "State": "running"},
                    {"Id": "2" * 64, "Names": ["/b"], "ImageID": image, "State": "exited"},
                ],
            ),
            "/images/json": httpx.Response(
                200,
                json=[
                    {"Id": image, "RepoTags": ["alpine:3.20"], "Size": 12, "Containers": -1},
                    {"Id": "sha256:" + "b" * 64, "RepoTags": None, "Size": 5},
                ],
            ),
        }
    )
    nodes = await adapter.list_children("images")
    counted = {node.name: node.containers for node in nodes if isinstance(node, ImageNode)}
    assert counted == {"alpine:3.20": 2, "<none> bbbbbbbbbbbb": 0}


def _frame(stream: int, text: bytes) -> bytes:
    return bytes([stream, 0, 0, 0]) + len(text).to_bytes(4, "big") + text


def test_log_lines_keep_their_time_and_stream() -> None:
    body = _frame(1, b"2026-11-21T11:22:14.567906709Z started\n") + _frame(
        2, b"2026-11-21T11:22:15Z oops\n"
    )
    assert log_rows(body, tty=False) == [
        ["2026-11-21T11:22:14.567906Z", "stdout", "started"],
        ["2026-11-21T11:22:15Z", "stderr", "oops"],
    ]


def test_a_tty_has_one_unframed_stream() -> None:
    body = b"2026-11-21T11:22:12.795255406Z line 1\r\n2026-11-21T11:22:12.795387532Z line 2\r\n"
    assert [row[1:] for row in log_rows(body, tty=True)] == [["stdout", "line 1"], ["stdout", "line 2"]]


def test_a_long_line_is_cut() -> None:
    body = b"2026-11-21T11:22:12Z " + b"x" * 20_000 + b"\n"
    [row] = log_rows(body, tty=True)
    assert row[2] is not None and len(row[2].encode()) <= 16 * 1024 + 3
