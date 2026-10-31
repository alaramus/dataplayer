"""The lab put into a ZooKeeper this server started (D302)."""

from typing import Any

from app.adapters.catalog import ZnodeNode
from app.adapters.zookeeper.samples import LAB, LAB_PASSWORD, LAB_USER
from tests.adapters.zookeeper_fixture import adapter, on_server


def _drop_lab(client: Any) -> None:
    client.add_auth("digest", f"{LAB_USER}:{LAB_PASSWORD}")
    if client.exists(LAB) is not None:
        client.delete(LAB, recursive=True)


async def test_the_lab_is_made_and_made_again_the_same() -> None:
    source = adapter()
    try:
        first = await source.install_sample_data()
        again = await source.install_sample_data()
        assert first == again and LAB in first

        level = {node.name: node for node in await source.list_children(LAB)}
        assert {"config", "services", "election", "queue", "counters", "private"} <= set(level)
        private = level["private"]
        assert isinstance(private, ZnodeNode) and not private.readable

        queue = await source.list_children(f"{LAB}/queue")
        assert len(queue) == 5 and all(node.name.startswith("job-") for node in queue)
        config = {node.name: node for node in await source.list_children(f"{LAB}/config")}
        assert [one.kind for one in config["billing"].representations][0] == "tree"
    finally:
        await on_server(_drop_lab)
