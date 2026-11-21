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
from app.adapters.views import (
    BooleanValue,
    BytesValue,
    DocumentView,
    EmptyValue,
    FieldsBlock,
    LinkValue,
    NoticeBlock,
    NumberValue,
    PairsBlock,
    SectionBlock,
    StateValue,
    TableBlock,
    ViewValue,
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
