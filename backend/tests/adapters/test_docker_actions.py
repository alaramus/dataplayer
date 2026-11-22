"""Changing a Docker daemon through an SSH server (D410–D412).

Needs `docker compose up -d docker-remote`. Each test makes what it changes,
so the stand's other containers stay as the read-only tests expect them.
"""

from typing import Any

import pytest

from app.adapters.actions import ActionRefused, JsonAction
from app.adapters.docker.adapter import DockerAdapter
from app.adapters.docker.connect import OpenAsConnection
from app.adapters.docker.session import DockerSession
from app.adapters.docker_api.client import EngineClient
from app.adapters.operations import ProducesJob
from tests.adapters.docker_stand import (
    IMAGE,
    Through,
    build_stand,
    make,
    open_through,
    options,
)


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


def _json(adapter: DockerAdapter, name: str) -> JsonAction[Any]:
    action = adapter.action(name)
    assert isinstance(action, JsonAction)
    return action


async def _state(engine: EngineClient, container: str) -> str:
    answer = await engine.request("GET", f"/containers/{container}/json", expected=(200,))
    return str(answer.json()["State"]["Status"])


async def _fresh(engine: EngineClient, name: str) -> str:
    await engine.request("DELETE", f"/containers/{name}", params={"force": "true"}, expected=(204, 404))
    return await make(engine, name, {"Image": IMAGE, "Cmd": ["sleep", "100000"]})


async def test_a_container_is_stopped_started_paused_and_carries_on(
    adapter: DockerAdapter, engine: EngineClient
) -> None:
    container = await _fresh(engine, "dp-test-life")
    node = f"container:{container}"
    start = _json(adapter, "docker_start")
    preview = await start.preview(node, {})  # type: ignore[attr-defined] # Previews
    assert preview.blocked and "already running" in preview.items[0]

    await _json(adapter, "docker_stop").perform(node, {"timeout": 1})
    assert await _state(engine, container) == "exited"
    await start.perform(node, {})
    assert await _state(engine, container) == "running"
    await _json(adapter, "docker_pause").perform(node, {})
    assert await _state(engine, container) == "paused"
    with pytest.raises(ActionRefused):
        await _json(adapter, "docker_pause").perform(node, {})
    await _json(adapter, "docker_unpause").perform(node, {})
    assert await _state(engine, container) == "running"
    await _json(adapter, "docker_kill").perform(node, {"signal": "SIGKILL"})
    assert await _state(engine, container) == "exited"


async def test_a_compose_project_is_restarted_as_its_containers(
    adapter: DockerAdapter, stand: dict[str, str], engine: EngineClient
) -> None:
    result = await _json(adapter, "docker_restart").perform("project:dp-test", {"timeout": 1})
    assert "1" in result.message
    assert await _state(engine, stand["web"]) == "running"
    assert "project:dp-test" in result.reload_node_ids


async def test_a_running_container_is_removed_only_with_force(
    adapter: DockerAdapter, engine: EngineClient
) -> None:
    container = await _fresh(engine, "dp-test-remove")
    node = f"container:{container}"
    remove = _json(adapter, "docker_remove_container")
    preview = await remove.preview(node, {"force": False})  # type: ignore[attr-defined] # Previews
    assert preview.blocked and "Force" in preview.summary
    with pytest.raises(ActionRefused):
        await remove.perform(node, {"force": False})
    await remove.perform(node, {"force": True, "volumes": True})
    gone = await engine.request("GET", f"/containers/{container}/json", expected=(200, 404))
    assert gone.status == 404


async def test_what_is_in_use_names_who_uses_it(
    adapter: DockerAdapter, stand: dict[str, str], engine: EngineClient
) -> None:
    del stand
    image = (await engine.request("GET", f"/images/{IMAGE}/json", expected=(200,))).json()["Id"]
    blocked = await _json(adapter, "docker_remove_image").preview(  # type: ignore[attr-defined] # Previews
        f"image:{image}", {"force": False}
    )
    assert blocked.blocked and "dp-test-web" in blocked.summary
    volume = await _json(adapter, "docker_remove_volume").preview(  # type: ignore[attr-defined] # Previews
        "volume:dp-test-data", {}
    )
    assert volume.blocked and "dp-test-web" in volume.summary
    networks = {
        one["Name"]: one["Id"]
        for one in (await engine.request("GET", "/networks", expected=(200,))).json()
    }
    remove_network = _json(adapter, "docker_remove_network")
    attached = await remove_network.preview(f"network:{networks['dp-test-net']}", {})  # type: ignore[attr-defined] # Previews
    assert attached.blocked and "dp-test-web" in attached.summary
    with pytest.raises(ActionRefused):
        await remove_network.perform(f"network:{networks['bridge']}", {})


async def test_a_volume_and_a_network_are_made_and_removed(
    adapter: DockerAdapter, engine: EngineClient
) -> None:
    await engine.request("DELETE", "/volumes/dp-test-made", expected=(204, 404))
    made = await _json(adapter, "docker_new_volume").perform("volumes", {"name": "dp-test-made"})
    assert made.created_node_id == "volume:dp-test-made"
    with pytest.raises(ActionRefused):
        await _json(adapter, "docker_new_volume").perform("volumes", {"name": "dp-test-made"})
    await _json(adapter, "docker_remove_volume").perform("volume:dp-test-made", {})

    await engine.request("DELETE", "/networks/dp-test-made-net", expected=(204, 404))
    network = await _json(adapter, "docker_new_network").perform(
        "networks", {"name": "dp-test-made-net", "internal": True}
    )
    assert network.created_node_id is not None
    inspected = await engine.request("GET", "/networks/dp-test-made-net", expected=(200,))
    assert inspected.json()["Internal"] is True
    prune = _json(adapter, "docker_prune_networks")
    preview = await prune.preview("networks", {})  # type: ignore[attr-defined] # Previews
    assert "dp-test-made-net" in preview.items
    assert "dp-test-net" not in preview.items
    await prune.perform("networks", {})
    gone = await engine.request("GET", "/networks/dp-test-made-net", expected=(200, 404))
    assert gone.status == 404


async def test_a_prune_preview_names_only_what_would_go(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    del stand
    containers = await _json(adapter, "docker_prune_containers").preview("containers", {})  # type: ignore[attr-defined] # Previews
    assert "dp-test-failed" in containers.items
    assert "dp-test-web" not in containers.items
    with pytest.raises(ActionRefused):
        await _json(adapter, "docker_prune_containers").perform("images", {})


async def test_a_pull_is_a_job_of_one_image(adapter: DockerAdapter, engine: EngineClient) -> None:
    pull = adapter.action("docker_pull")
    assert isinstance(pull, ProducesJob)
    await engine.request("DELETE", "/images/busybox:1.36", expected=(200, 404, 409))
    raw = {"reference": "busybox:1.36"}
    preview = await pull.preview("images", raw)  # type: ignore[attr-defined] # Previews
    assert preview.fingerprint is not None
    plan = await pull.plan_job("images", raw, preview.fingerprint)
    [target] = plan.targets
    assert await pull.run_unit("images", raw, plan.unit_fingerprint, target) == "completed"
    assert await pull.observe("images", raw, plan.targets) == ["as_requested"]


async def test_a_private_image_is_said_to_be_unsupported(adapter: DockerAdapter) -> None:
    pull = adapter.action("docker_pull")
    assert isinstance(pull, ProducesJob)
    raw = {"reference": "dataplayer/no-such-image-xyz:1"}
    preview = await pull.preview("images", raw)  # type: ignore[attr-defined] # Previews
    assert preview.fingerprint is not None
    plan = await pull.plan_job("images", raw, preview.fingerprint)
    with pytest.raises(ActionRefused) as refused:
        await pull.run_unit("images", raw, plan.unit_fingerprint, plan.targets[0])
    assert "private registries" in refused.value.message


async def test_a_container_is_committed_to_an_image(
    adapter: DockerAdapter, engine: EngineClient
) -> None:
    container = await _fresh(engine, "dp-test-commit")
    commit = adapter.action("docker_commit")
    assert isinstance(commit, ProducesJob)
    raw = {"repository": "dp-test/committed", "tag": "v1"}
    node = f"container:{container}"
    preview = await commit.preview(node, raw)  # type: ignore[attr-defined] # Previews
    assert preview.fingerprint is not None
    plan = await commit.plan_job(node, raw, preview.fingerprint)
    assert await commit.run_unit(node, raw, plan.unit_fingerprint, plan.targets[0]) == "completed"
    assert await commit.observe(node, raw, plan.targets) == ["as_requested"]
    await engine.request("DELETE", "/images/dp-test/committed:v1", expected=(200,))
    await engine.request("DELETE", f"/containers/{container}", params={"force": "true"}, expected=(204,))


async def test_what_a_node_offers(adapter: DockerAdapter, stand: dict[str, str]) -> None:
    def names(actions: list[Any]) -> set[str]:
        return {action.name for action in actions}

    assert "docker_commit" in names(await adapter.available(f"container:{stand['web']}"))
    assert "docker_start" in names(await adapter.available("project:dp-test"))
    assert names(await adapter.available("standalone")) == set()
    assert names(await adapter.available("images")) == {"docker_pull", "docker_prune_images"}
    assert names(await adapter.available(f"container:{stand['web']}/logs")) == set()
    assert names(await adapter.available("system/engine")) == set()


async def test_a_container_puts_its_actions_over_its_view_by_icon(
    adapter: DockerAdapter, stand: dict[str, str]
) -> None:
    # D424: everything done to one container, each with a picture to draw.
    offered = await adapter.available(f"container:{stand['web']}")
    over_view = {action.name: action.icon for action in offered if action.in_view}
    assert set(over_view) == {
        "docker_start",
        "docker_stop",
        "docker_restart",
        "docker_pause",
        "docker_unpause",
        "docker_kill",
        "docker_remove_container",
        "docker_commit",
        "docker_terminal",
    }
    assert all(over_view.values())
    # Offered only on a database's container, which the stand's is not.
    assert OpenAsConnection.in_view and OpenAsConnection.icon

