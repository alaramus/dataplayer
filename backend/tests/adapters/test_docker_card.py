"""A container's view, built from inspects recorded on the stand (D422, D421).

`docker_inspects/` holds what `docker inspect` answered for `dp-test-web`
(running, no health check, a volume, Compose labels), `dp-test-failed` (exited
with 3) and a container with a passing health check, published ports, limits
and secrets in its environment. Changes on top of a recording are made here,
where a test can be read.
"""

import copy
import json
from pathlib import Path
from typing import Any

from app.adapters.docker.card import container_view, is_sensitive
from app.adapters.docker.cards import image_view, network_view, volume_view
from app.adapters.views import (
    BooleanValue,
    BytesValue,
    DocumentView,
    EmptyValue,
    FieldsBlock,
    LinkValue,
    ListValue,
    NoticeBlock,
    NumberValue,
    PairsBlock,
    SectionBlock,
    StateValue,
    TableBlock,
    ViewValue,
    code,
    text,
)

RECORDED = Path(__file__).parent / "docker_inspects"


def _recorded(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((RECORDED / f"{name}.json").read_text(encoding="utf-8"))
    return loaded


def _section(view: DocumentView, title: str) -> SectionBlock:
    for block in view.blocks:
        if isinstance(block, SectionBlock) and block.title == title:
            return block
    raise AssertionError(f"no section {title}")


def _titles(view: DocumentView) -> list[str]:
    return [block.title for block in view.blocks if isinstance(block, SectionBlock)]


def _fields(view: DocumentView, title: str) -> dict[str, ViewValue]:
    found: dict[str, ViewValue] = {}
    for block in _section(view, title).blocks:
        if isinstance(block, FieldsBlock):
            found.update({one.label: one.value for one in block.fields})
    return found


def _tables(view: DocumentView, title: str) -> list[TableBlock]:
    return [block for block in _section(view, title).blocks if isinstance(block, TableBlock)]


def _notices(view: DocumentView) -> list[NoticeBlock]:
    return [block for block in view.blocks if isinstance(block, NoticeBlock)]


def test_a_running_container_without_a_health_check() -> None:
    inspect = _recorded("running")
    view = container_view(inspect)
    assert view.header.title == "dp-test-web"
    assert view.header.state == StateValue(word="running", tone="good")
    image = view.header.subtitle
    assert isinstance(image, LinkValue)
    assert image.text == "alpine:3.20"
    assert image.node_id == f"image:{inspect['Image']}"
    assert _titles(view) == ["Overview", "Network", "Storage", "Environment", "Labels", "Resources"]
    overview = _fields(view, "Overview")
    assert "Started" in overview and "Exit code" not in overview
    project = overview["Compose project"]
    assert isinstance(project, LinkValue) and project.node_id == "project:dp-test"
    assert isinstance(overview["User"], EmptyValue)
    [mounts] = _tables(view, "Storage")
    kind, source, destination, writable = mounts.rows[0]
    assert isinstance(source, LinkValue) and source.node_id == "volume:dp-test-data"
    assert writable == BooleanValue(value=True)
    networks = _tables(view, "Network")[1]
    network = networks.rows[0][0]
    assert isinstance(network, LinkValue) and network.text == "dp-test-net"
    assert _section(view, "Labels").collapsed
    resources = _fields(view, "Resources")
    assert all(isinstance(value, EmptyValue) for value in resources.values())
    assert _notices(view) == []


def test_a_healthy_container_shows_its_checks_ports_and_limits() -> None:
    view = container_view(_recorded("healthy"))
    assert view.header.state == StateValue(word="healthy", tone="good")
    assert "Health" in _titles(view)
    health = _fields(view, "Health")
    assert health["Status"] == StateValue(word="healthy", tone="good")
    assert health["Failing streak"] == NumberValue(value=0)
    [checks] = _tables(view, "Health")
    assert checks.columns == ["Started", "Exit code", "Output"]
    assert len(checks.rows) >= 1
    ports = _tables(view, "Network")[0]
    # One row per address the port is published on, IPv4 and IPv6 alike.
    assert [(row[0], row[1], row[2]) for row in ports.rows] == [
        (text("80/tcp"), text("0.0.0.0"), text("8089")),
        (text("80/tcp"), text("::"), text("8089")),
    ]
    resources = _fields(view, "Resources")
    assert resources["Memory limit"] == BytesValue(value=64 * 1024 * 1024)
    cpus = resources["CPU limit"]
    assert isinstance(cpus, NumberValue) and cpus.value == 0.5
    policy = _fields(view, "Overview")["Restart policy"]
    assert getattr(policy, "text", None) == "unless-stopped"


def test_a_sensitive_variable_is_marked_by_its_name() -> None:
    view = container_view(_recorded("healthy"))
    [environment] = _section(view, "Environment").blocks
    assert isinstance(environment, PairsBlock)
    marked = {pair.name: pair.sensitive for pair in environment.pairs}
    assert marked["DB_PASSWORD"] is True
    assert marked["API_TOKEN"] is True
    assert marked["PLAIN"] is False
    assert marked["PATH"] is False
    # Hidden from a glance, not withheld (D421).
    assert {pair.name: pair.value for pair in environment.pairs}["DB_PASSWORD"] == "hunter2"


def test_names_are_judged_case_folded() -> None:
    assert is_sensitive("ssh_private_key")
    assert is_sensitive("Aws_Secret")
    assert is_sensitive("PGPASSWD")
    assert not is_sensitive("HOME")


def test_a_failed_container_says_its_exit_code() -> None:
    view = container_view(_recorded("failed"))
    assert view.header.state == StateValue(word="failed", tone="bad")
    overview = _fields(view, "Overview")
    assert overview["Exit code"] == NumberValue(value=3)
    assert "Finished" in overview and "Started" not in overview
    assert "Health" not in _titles(view)


def test_a_container_that_stopped_cleanly_is_neutral() -> None:
    inspect = copy.deepcopy(_recorded("failed"))
    inspect["State"]["ExitCode"] = 0
    assert container_view(inspect).header.state == StateValue(word="stopped", tone="neutral")


def test_an_unhealthy_one_is_bad_and_a_starting_one_busy() -> None:
    inspect = copy.deepcopy(_recorded("healthy"))
    inspect["State"]["Health"]["Status"] = "unhealthy"
    assert container_view(inspect).header.state == StateValue(word="unhealthy", tone="bad")
    inspect["State"]["Health"]["Status"] = "starting"
    assert container_view(inspect).header.state == StateValue(word="starting", tone="busy")
    inspect["State"]["Status"] = "paused"
    assert container_view(inspect).header.state == StateValue(word="paused", tone="warning")


def test_restarts_and_memory_kills_are_told() -> None:
    inspect = copy.deepcopy(_recorded("failed"))
    inspect["RestartCount"] = 14
    inspect["State"]["OOMKilled"] = True
    notices = _notices(container_view(inspect))
    assert [notice.tone for notice in notices] == ["bad", "warning"]
    assert "14" in notices[1].text


def test_a_few_restarts_are_not_told() -> None:
    inspect = copy.deepcopy(_recorded("failed"))
    inspect["RestartCount"] = 3
    assert _notices(container_view(inspect)) == []


def test_a_view_survives_the_json_it_crosses_as() -> None:
    view = container_view(_recorded("healthy"))
    assert DocumentView.model_validate_json(view.model_dump_json()) == view


# --- an image, a volume and a network (D422, slice 2) ------------------------
# `image.json`, `volume.json` and `network.json` are alpine:3.20, dp-test-data
# and dp-test-net as the stand's daemon answered; `containers.json` is the
# stand's dp-test containers as the list answers them.


def _containers() -> list[dict[str, Any]]:
    listed: list[dict[str, Any]] = json.loads((RECORDED / "containers.json").read_text(encoding="utf-8"))
    return listed


def test_an_image_shows_its_tags_size_and_who_runs_it() -> None:
    inspect = _recorded("image")
    view = image_view(inspect, _containers())
    assert view.header.title == "alpine:3.20"
    overview = _fields(view, "Overview")
    tags = overview["Tags"]
    assert isinstance(tags, ListValue) and "alpine:3.20" in tags.items
    assert overview["Size"] == BytesValue(value=inspect["Size"])
    layers = overview["Layers"]
    assert isinstance(layers, LinkValue) and layers.node_id == f"image:{inspect['Id']}/history"
    [users] = _tables(view, "Containers")
    names = [row[0] for row in users.rows]
    assert all(isinstance(one, LinkValue) for one in names)
    assert {one.text for one in names if isinstance(one, LinkValue)} >= {"dp-test-web", "dp-test-failed"}
    states = {row[0].text: row[1] for row in users.rows if isinstance(row[0], LinkValue)}
    assert states["dp-test-failed"] == StateValue(word="failed", tone="bad")


def test_an_image_nobody_runs_has_an_empty_table_not_a_missing_one() -> None:
    view = image_view(_recorded("image"), [])
    [users] = _tables(view, "Containers")
    assert users.rows == []


def test_a_volume_names_who_mounts_it_and_where() -> None:
    view = volume_view(_recorded("volume"), _containers())
    assert view.header.title == "dp-test-data"
    overview = _fields(view, "Overview")
    assert overview["Mount point"] == code("/var/lib/docker/volumes/dp-test-data/_data")
    [mounts] = _tables(view, "Containers")
    assert len(mounts.rows) == 1
    who, state, destination, writable = mounts.rows[0]
    assert isinstance(who, LinkValue) and who.text == "dp-test-web"
    assert destination == code("/data")
    assert writable == BooleanValue(value=True)
    assert state == StateValue(word="running", tone="good")


def test_a_network_shows_its_subnets_and_containers_with_addresses() -> None:
    inspect = _recorded("network")
    view = network_view(inspect)
    assert view.header.title == "dp-test-net"
    [subnets] = _tables(view, "Addresses")
    assert subnets.rows[0][:2] == [text("172.20.0.0/16"), text("172.20.0.1")]
    [attached] = _tables(view, "Containers")
    who, ipv4, ipv6, _ = attached.rows[0]
    assert isinstance(who, LinkValue) and who.node_id.startswith("container:")
    assert ipv4 == text("172.20.0.2/16")
    assert isinstance(ipv6, EmptyValue)
    assert _fields(view, "Overview")["Internal"] == BooleanValue(value=False)
    assert _section(view, "Labels").collapsed


def test_every_view_survives_the_json_it_crosses_as() -> None:
    for view in (
        image_view(_recorded("image"), _containers()),
        volume_view(_recorded("volume"), _containers()),
        network_view(_recorded("network")),
    ):
        assert DocumentView.model_validate_json(view.model_dump_json()) == view
