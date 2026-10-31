"""What a ZooKeeper connection can be asked to do to its znodes (D300)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from kazoo.security import make_digest_acl

from app.adapters.actions import (
    ActionRefused,
    OffersFieldHints,
    Previews,
)
from app.adapters.zookeeper.actions import (
    SUBTREE_CEILING,
    acl_text,
    keeps_admin,
    parse_acl,
)
from app.adapters.zookeeper.adapter import ZookeeperAdapter
from tests.adapters.zookeeper_fixture import (
    SECRET_PASSWORD,
    SECRET_USER,
    adapter,
    build_tree,
    digest_options,
    new_root,
    on_server,
    remove_tree,
)


@pytest.fixture
async def root() -> AsyncIterator[str]:
    path = new_root()
    await on_server(lambda client: build_tree(client, path))
    yield path
    await on_server(lambda client: remove_tree(client, path))


async def _perform(
    source: ZookeeperAdapter, action: str, node_id: str | None, **raw: Any
) -> Any:
    return await source.action(action).perform(node_id, raw)  # type: ignore[attr-defined]


def _exists(path: str) -> Any:
    return on_server(lambda client: client.exists(path))


# --- making znodes -----------------------------------------------------------


async def test_a_znode_is_made_under_the_selected_one_with_its_data(root: str) -> None:
    result = await _perform(
        adapter(), "new_child_znode", f"{root}/services", name="fresh", data='{"a": 1}'
    )
    assert result.created_node_id == f"{root}/services/fresh"
    assert result.reload_node_ids == [f"{root}/services"]
    data, _ = await on_server(lambda client: client.get(f"{root}/services/fresh"))
    assert data == b'{"a": 1}'


async def test_a_sequential_znode_gets_the_number_zookeeper_chooses(root: str) -> None:
    result = await _perform(
        adapter(), "new_child_znode", root, name="job-", sequential=True
    )
    made = result.created_node_id
    assert made.startswith(f"{root}/job-") and made[-10:].isdigit()


async def test_a_znode_at_the_top_is_made_under_the_root_path(root: str) -> None:
    confined = adapter(chroot=root)
    result = await _perform(confined, "new_top_znode", None, name="top")
    assert result.created_node_id == "/top"
    assert result.reload_node_ids == [None]
    assert await _exists(f"{root}/top") is not None


async def test_a_taken_name_is_refused_as_a_conflict(root: str) -> None:
    with pytest.raises(ActionRefused) as refused:
        await _perform(adapter(), "new_child_znode", root, name="config")
    assert refused.value.reason == "conflict"


@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "tab\there"])
async def test_a_name_that_is_not_one_part_of_a_path_is_refused(
    root: str, name: str
) -> None:
    with pytest.raises(ValueError):
        await _perform(adapter(), "new_child_znode", root, name=name)


# --- deleting ----------------------------------------------------------------


async def test_a_childless_znode_is_deleted_and_one_with_children_is_not(
    root: str,
) -> None:
    source = adapter()
    result = await _perform(source, "delete_znode", f"{root}/text")
    assert result.reload_node_ids == [root]
    assert await _exists(f"{root}/text") is None

    with pytest.raises(ActionRefused) as refused:
        await _perform(source, "delete_znode", f"{root}/services")
    assert refused.value.reason == "conflict"
    assert await _exists(f"{root}/services") is not None


async def test_a_subtree_is_previewed_then_deleted_whole(root: str) -> None:
    source = adapter()
    action = source.action("delete_subtree")
    assert isinstance(action, Previews)
    preview = await action.preview(f"{root}/services", {})
    # 25 items, one grandchild, and the znode itself.
    assert "27" in preview.summary
    assert preview.items[0] == f"{root}/services/item-00/deeper"
    # Twenty paths, then how many more.
    assert len(preview.items) == 21 and preview.items[-1] == "and 7 more"

    result = await _perform(source, "delete_subtree", f"{root}/services")
    assert "27" in result.message
    assert await _exists(f"{root}/services") is None


async def test_the_servers_own_subtree_and_the_top_are_not_deleted() -> None:
    action = adapter().action("delete_subtree")
    assert isinstance(action, Previews)
    with pytest.raises(ActionRefused):
        await action.preview("/zookeeper", {})
    with pytest.raises(ActionRefused):
        await action.preview("/", {})


async def test_a_subtree_this_connection_cannot_list_is_not_deleted(root: str) -> None:
    def lock(client: Any) -> None:
        client.create(
            f"{root}/vault/inner",
            b"",
            makepath=True,
        )
        client.set_acls(
            f"{root}/vault/inner",
            [make_digest_acl(SECRET_USER, SECRET_PASSWORD, all=True)],
        )

    await on_server(lock)
    with pytest.raises(ActionRefused):
        await _perform(adapter(), "delete_subtree", f"{root}/vault")
    assert await _exists(f"{root}/vault") is not None


def test_the_ceiling_is_stated() -> None:
    assert SUBTREE_CEILING >= 1000


# --- the ACL -----------------------------------------------------------------


def test_an_acl_reads_back_as_it_was_written() -> None:
    text = "world:anyone:r\ndigest:ops:abc=:cdrwa\nip:10.0.0.1:rw"
    assert acl_text(parse_acl(text)) == text


@pytest.mark.parametrize(
    "text", ["", "world:anyone", "world:anyone:x", "world:anyone:rr", ":anyone:r"]
)
def test_an_acl_that_is_not_one_is_refused(text: str) -> None:
    with pytest.raises(ValueError):
        parse_acl(text)


def test_whether_the_connection_keeps_admin() -> None:
    assert keeps_admin(parse_acl("world:anyone:cdrwa"), None)
    assert not keeps_admin(parse_acl("world:anyone:r"), None)
    assert keeps_admin(parse_acl("digest:ops:x=:a"), "ops")
    assert not keeps_admin(parse_acl("digest:ops:x=:a"), "ann")


async def test_the_acl_form_opens_with_the_acl_the_znode_has(root: str) -> None:
    action = adapter().action("change_acl")
    assert isinstance(action, OffersFieldHints)
    hints = await action.field_hints(f"{root}/config")
    assert hints.values == {"acl": "world:anyone:cdrwa"}


async def test_an_acl_is_changed_with_a_warning_when_it_locks_this_connection_out(
    root: str,
) -> None:
    source = adapter()
    action = source.action("change_acl")
    assert isinstance(action, Previews)
    preview = await action.preview(f"{root}/config", {"acl": "world:anyone:r"})
    assert preview.items[0] == "world:anyone:r"
    assert any("Warning" in item for item in preview.items)

    await _perform(source, "change_acl", f"{root}/config", acl="world:anyone:r")
    entries, _ = await on_server(lambda client: client.get_acls(f"{root}/config"))
    assert acl_text(entries) == "world:anyone:r"


async def test_an_acl_is_changed_on_a_whole_subtree(root: str) -> None:
    source = ZookeeperAdapter(digest_options())
    acl = "world:anyone:cdrw\nauth::cdrwa"
    await _perform(source, "change_acl", f"{root}/services", acl=acl, recursive=True)

    def read(client: Any) -> list[str]:
        return [
            acl_text(client.get_acls(path)[0])
            for path in (f"{root}/services", f"{root}/services/item-00/deeper")
        ]

    found = await on_server(read)
    # `auth` stands for the identities of the session that set it.
    assert all("world:anyone:cdrw" in one and "digest:keeper:" in one for one in found)


async def test_every_action_is_offered_at_the_top() -> None:
    names = [action.name for action in await adapter().available(None)]
    assert names == [
        "new_top_znode",
        "new_child_znode",
        "delete_znode",
        "delete_subtree",
        "change_acl",
    ]
