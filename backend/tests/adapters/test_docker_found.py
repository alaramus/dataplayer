"""Metrics, search and a container as a connection, against the stand (D415–D417).

Needs `docker compose up -d docker-remote`.
"""

import time

import pytest

from app.adapters.actions import PreparesConnector
from app.adapters.docker import metrics
from app.adapters.docker.adapter import DockerAdapter
from app.adapters.docker.session import DockerSession
from app.adapters.docker_api.client import EngineClient
from app.adapters.search import NodeSearchRequest, SearchBounds
from tests.adapters.docker_stand import (
    IMAGE,
    PROJECT,
    THROUGH,
    Through,
    build_stand,
    make,
    open_through,
    options,
)

# An image no type declares, tagged as one a type does: the draft is read off
# what the daemon says, so no database has to be pulled for it.
DATABASE_TAG = "postgres:dp-test"


@pytest.fixture(scope="module")
async def through() -> Through:
    return await open_through()


@pytest.fixture(scope="module")
async def stand(through: Through) -> dict[str, str]:
    return await build_stand(through)


@pytest.fixture
def adapter(through: Through, stand: dict[str, str]) -> DockerAdapter:
    del stand
    return DockerAdapter(options(), through)


@pytest.fixture
async def engine(through: Through, stand: dict[str, str]) -> EngineClient:
    del stand
    return await DockerSession(options(), through).engine()


def _bounds() -> SearchBounds:
    return SearchBounds(deadline=time.monotonic() + 30)


async def test_running_containers_are_measured_and_the_rest_counted(
    adapter: DockerAdapter,
) -> None:
    found = await adapter.metric_samples()
    web = {s.field: s for s in found if s.metric == "container" and s.label == "dp-test-web"}
    assert web["cpu"].value >= 0
    assert web["memory"].value > 0
    assert web["network_in"].counter
    assert not [s for s in found if s.label == "dp-test-failed"]
    engine = {s.field: s.value for s in found if s.metric == "engine"}
    assert engine["containers_running"] >= 2
    assert engine["containers_stopped"] >= 1
    assert engine["skipped"] == 0


async def test_past_the_ceiling_the_running_are_counted_as_skipped(
    adapter: DockerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(metrics, "POLLED", 1)
    found = await adapter.metric_samples()
    measured = {s.label for s in found if s.metric == "container"}
    skipped = next(s.value for s in found if s.field == "skipped")
    assert len(measured) == 1
    assert skipped >= 1


async def test_a_search_finds_each_kind_by_name(adapter: DockerAdapter) -> None:
    async def names(query: str, node_id: str | None = None) -> dict[str, str]:
        result = await adapter.search_nodes(NodeSearchRequest(query=query, node_id=node_id))
        return {match.node.name: match.location for match in result.matches}

    assert (await names("dp-test-web")) == {"dp-test-web": f"Containers · {PROJECT}"}
    assert PROJECT in await names(PROJECT)
    assert (await names("dp-test-data")) == {"dp-test-data": "Volumes"}
    assert (await names("dp-test-net")) == {"dp-test-net": "Networks"}
    # An image by any of its tags.
    assert IMAGE in await names("alpine")
    # Within a project, its containers only; a container is not a level.
    within = await names("dp-test", f"project:{PROJECT}")
    assert set(within) == {"dp-test-web"}
    with pytest.raises(ValueError):
        await names("x", "volume:dp-test-data")


async def test_every_name_is_kept_under_its_level(adapter: DockerAdapter) -> None:
    batches = [batch async for batch in adapter.enumerate_names(10_000, _bounds())]
    kept = {name.node.name: name for batch in batches for name in batch.names}
    assert kept["dp-test-web"].scope == f"project:{PROJECT}"
    assert kept["dp-test-tty"].scope == "standalone"
    assert kept[PROJECT].scope == "containers"
    assert kept["dp-test-data"].scope == "volumes"
    assert [a.node_id for a in kept["dp-test-web"].ancestors or []] == [
        "containers",
        f"project:{PROJECT}",
    ]


async def test_a_database_container_becomes_a_draft_through_the_same_ssh(
    adapter: DockerAdapter, engine: EngineClient
) -> None:
    repository, _, tag = DATABASE_TAG.partition(":")
    await engine.request(
        "POST",
        f"/images/{IMAGE}/tag",
        params={"repo": repository, "tag": tag},
        expected=(201,),
    )
    container = await make(
        engine,
        "dp-test-db",
        {
            "Image": DATABASE_TAG,
            "Cmd": ["sleep", "100000"],
            "Env": ["POSTGRES_USER=shop", "POSTGRES_PASSWORD=secret"],
            "ExposedPorts": {"5432/tcp": {}},
            "HostConfig": {"PortBindings": {"5432/tcp": [{"HostPort": ""}]}},
        },
    )
    try:
        node_id = f"container:{container}"
        offered = {action.name for action in await adapter.available(node_id)}
        assert "docker_open_as_connection" in offered
        action = adapter.action("docker_open_as_connection")
        assert isinstance(action, PreparesConnector)
        draft = await action.prepare_connector(node_id, {})
        assert draft.name == "dp-test-db"
        assert draft.adapter_type == "postgres"
        published = draft.options.pop("port")
        assert isinstance(published, int) and published > 0 and published != 5432
        assert draft.options == {
            "auth_method": "user_password",
            "user": "shop",
            "database": "shop",
            "password": "secret",
            "host": "127.0.0.1",
            "ssh_tunnel": THROUGH,
        }
    finally:
        await engine.request(
            "DELETE", f"/containers/{container}", params={"force": "true"}, expected=(204, 404)
        )


async def test_a_container_of_no_declared_image_is_not_offered(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    offered = {action.name for action in await adapter.available(f"container:{stand['web']}")}
    assert "docker_terminal" in offered
    assert "docker_open_as_connection" not in offered
