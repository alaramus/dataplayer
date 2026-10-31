"""ZooKeeper as a source: reaching it, its tree, a znode's data, stat and children (D297, D298)."""

import json
from collections.abc import AsyncIterator

import pytest

from app.adapters.catalog import ZnodeNode
from app.adapters.content import (
    ContentConflict,
    ContentRequest,
    EditorContentRequest,
    JsonContent,
    JsonObject,
    TextContent,
    UpdateContentRequest,
)
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import NodeNotFound
from app.adapters.summary import ZnodeContents
from app.adapters.zookeeper.adapter import ZookeeperAdapter
from app.adapters.zookeeper.options import ZookeeperAnonymous
from app.adapters.zookeeper.session import options_from_url
from tests.adapters.zookeeper_fixture import (
    BINARY,
    CHILDREN,
    CONFIG,
    SECRET_PASSWORD,
    SECRET_USER,
    adapter,
    build_tree,
    digest_options,
    new_root,
    on_server,
    options,
    remove_tree,
)


@pytest.fixture(scope="module")
async def root() -> AsyncIterator[str]:
    path = new_root()
    await on_server(lambda client: build_tree(client, path))
    yield path
    await on_server(lambda client: remove_tree(client, path))


def _znodes(nodes: list[object]) -> dict[str, ZnodeNode]:
    return {node.name: node for node in nodes if isinstance(node, ZnodeNode)}


# --- reaching it (D297) -------------------------------------------------------


async def test_a_connection_is_checked() -> None:
    result = await adapter().check_connection()
    assert result.ok, result.message
    assert result.latency_ms is not None


async def test_a_closed_port_is_a_network_failure_without_the_address() -> None:
    result = await ZookeeperAdapter(
        ZookeeperAnonymous(host="127.0.0.1", port=1)
    ).check_connection()
    assert not result.ok
    assert result.error_kind in {"network", "timeout"}
    assert "127.0.0.1" not in result.message


async def test_a_root_path_that_is_not_there_is_said(root: str) -> None:
    result = await adapter(chroot=f"{root}/nowhere").check_connection()
    assert not result.ok
    assert result.error_kind == "config"


async def test_the_server_says_its_version() -> None:
    features = await adapter().source_features()
    assert features.server_version is not None
    assert features.server_version.startswith("ZooKeeper 3.")


def test_a_connect_string_fills_the_form() -> None:
    assert options_from_url("zk.example.com:2181/apps/billing") == {
        "host": "zk.example.com",
        "port": 2181,
        "auth_method": "anonymous",
        "chroot": "/apps/billing",
    }
    assert options_from_url("zookeeper://[::1]") == {
        "host": "::1",
        "auth_method": "anonymous",
    }


@pytest.mark.parametrize(
    "url", ["a:2181,b:2181", "user@zk:2181", "zk:99999", "zk:2181/a//b", "/only/a/path"]
)
def test_a_connect_string_this_source_cannot_use_is_refused(url: str) -> None:
    with pytest.raises(ValueError):
        options_from_url(url)


@pytest.mark.parametrize("chroot", ["apps", "/apps/", "/apps/../etc", "/a//b"])
def test_a_root_path_must_be_a_path(chroot: str) -> None:
    with pytest.raises(ValueError):
        ZookeeperAnonymous(host="zk", chroot=chroot)


def test_the_connection_string_names_the_root_path_and_no_password() -> None:
    source = ZookeeperAdapter(digest_options(chroot="/apps"))
    assert source.connection_string().endswith("/apps")
    assert SECRET_PASSWORD not in source.connection_string()


# --- the tree (D298) ----------------------------------------------------------


async def test_the_top_holds_zookeepers_own_subtree_marked_as_its_own(
    root: str,
) -> None:
    top = _znodes(await adapter().list_children(None))
    assert top["zookeeper"].is_system
    assert not top[root[1:]].is_system


async def test_a_level_tells_its_znodes_apart(root: str) -> None:
    level = _znodes(await adapter().list_children(root))
    assert list(level) == sorted(level)

    config = level["config"]
    assert [one.kind for one in config.representations] == ["tree", "text"]
    assert not config.has_children
    assert config.data_length == len(json.dumps(CONFIG))

    assert [one.kind for one in level["text"].representations] == ["text"]
    # Larger than what is read to tell JSON from text: opened as text.
    assert [one.kind for one in level["big"].representations] == ["text"]

    services = level["services"]
    assert services.has_children and services.children == CHILDREN
    # Nothing to read but its children, so they come first.
    assert [one.kind for one in services.representations] == ["table", "text"]
    assert services.summarizable


async def test_a_znode_with_data_and_children_offers_its_data_first(root: str) -> None:
    services = _znodes(await adapter().list_children(f"{root}/services"))
    item = services["item-00"]
    assert item.has_children
    assert [one.kind for one in item.representations] == ["text", "table"]


async def test_the_way_down_to_a_znode_is_every_znode_above_it(root: str) -> None:
    path = await adapter().path_to(f"{root}/services/item-00/deeper")
    assert [node.id for node in path] == [
        root,
        f"{root}/services",
        f"{root}/services/item-00",
        f"{root}/services/item-00/deeper",
    ]


async def test_a_root_path_confines_the_tree(root: str) -> None:
    confined = adapter(chroot=root)
    names = set(_znodes(await confined.list_children(None)))
    assert {"config", "services", "secret"} <= names
    assert "zookeeper" not in names
    content = await confined.read_content(
        ContentRequest(node_id="/text", representation="text")
    )
    assert isinstance(content, TextContent) and content.text.startswith("plain words")


@pytest.mark.parametrize("node_id", ["relative", "/a/", "/a//b", "/a/../b", "/a/./b"])
async def test_an_id_this_source_did_not_issue_is_refused(node_id: str) -> None:
    with pytest.raises(ValueError):
        await adapter().list_children(node_id)


async def test_a_znode_that_is_not_there_is_not_found(root: str) -> None:
    with pytest.raises(ValueError):
        await adapter().list_children(f"{root}/gone")
    with pytest.raises(NodeNotFound):
        await adapter().node_summary(f"{root}/gone")


# --- children as rows ---------------------------------------------------------


async def test_children_are_paged_by_name(root: str) -> None:
    source = adapter()
    first = await source.fetch(FetchRequest(node_id=f"{root}/services", limit=10))
    assert [row[0] for row in first.rows] == [
        f"item-{index:02d}" for index in range(10)
    ]
    assert first.has_more
    last = await source.fetch(
        FetchRequest(node_id=f"{root}/services", offset=20, limit=10)
    )
    assert [row[0] for row in last.rows] == [
        f"item-{index:02d}" for index in range(20, 25)
    ]
    assert not last.has_more

    names = [column.name for column in first.columns]
    row = dict(zip(names, first.rows[0], strict=True))
    assert row["data"] == "value 0"
    assert row["children"] == "1"
    assert row["version"] == "0"
    assert row["modified"] is not None and row["modified"].endswith("Z")
    assert row["ephemeral_owner"] is None
    assert not any(
        column.sortable or column.filter_operators for column in first.columns
    )


async def test_a_child_too_large_to_preview_says_only_its_size(root: str) -> None:
    page = await adapter().fetch(FetchRequest(node_id=root, limit=100))
    names = [column.name for column in page.columns]
    rows = {row[0]: dict(zip(names, row, strict=True)) for row in page.rows}
    assert rows["big"]["data"] is None
    assert int(rows["big"]["bytes"] or 0) > 8000
    assert rows["binary"]["data"] == "0x" + BINARY.hex()
    assert rows["services"]["data"] == ""


# --- the data -----------------------------------------------------------------


async def test_json_data_is_read_as_a_tree(root: str) -> None:
    content = await adapter().read_content(
        ContentRequest(node_id=f"{root}/config", representation="tree")
    )
    assert isinstance(content, JsonContent)
    assert isinstance(content.value, JsonObject)
    assert [entry.name for entry in content.value.entries] == [
        "name",
        "replicas",
        "tags",
    ]


async def test_text_asked_for_as_a_tree_is_given_as_its_source(root: str) -> None:
    content = await adapter().read_content(
        ContentRequest(node_id=f"{root}/text", representation="tree")
    )
    assert isinstance(content, JsonContent)
    assert content.value is None and content.notice is not None


async def test_binary_data_is_shown_as_hex_and_not_offered_for_editing(
    root: str,
) -> None:
    source = adapter()
    content = await source.read_content(
        ContentRequest(node_id=f"{root}/binary", representation="text")
    )
    assert isinstance(content, TextContent)
    assert content.text.startswith("00000000  fa fb fc fd fe ff 00 01")
    assert content.notice is not None
    editor = await source.read_editor_content(
        EditorContentRequest(node_id=f"{root}/binary")
    )
    assert not editor.writable and editor.reason is not None


async def test_data_is_written_against_the_version_read(root: str) -> None:
    source = adapter()
    path = f"{root}/config"
    editor = await source.read_editor_content(EditorContentRequest(node_id=path))
    assert editor.writable and editor.validation == "json"
    assert editor.version is not None

    changed = '{"name": "billing", "replicas": 5}'
    updated = await source.update_content(
        UpdateContentRequest(node_id=path, text=changed, version=editor.version)
    )
    assert updated.version != editor.version
    data = await on_server(lambda client: client.get(path)[0])
    assert data == changed.encode()

    # The version the editor held is now an old one.
    with pytest.raises(ContentConflict):
        await source.update_content(
            UpdateContentRequest(node_id=path, text="{}", version=editor.version)
        )


async def test_a_znode_made_again_is_not_the_one_read(root: str) -> None:
    source = adapter()
    path = f"{root}/remade"
    await on_server(lambda client: client.create(path, b"first"))
    editor = await source.read_editor_content(EditorContentRequest(node_id=path))
    assert editor.version is not None

    def remake(client: object) -> None:
        client.delete(path)  # type: ignore[attr-defined]
        client.create(path, b"second")  # type: ignore[attr-defined]

    await on_server(remake)
    with pytest.raises(ContentConflict):
        await source.update_content(
            UpdateContentRequest(node_id=path, text="third", version=editor.version)
        )


# --- what a znode is, and who may read it ------------------------------------


async def test_a_summary_holds_the_stat_and_the_acl(root: str) -> None:
    summary = await adapter().node_summary(f"{root}/services")
    assert summary.kind == "znode"
    contents = summary.contents
    assert isinstance(contents, ZnodeContents)
    assert contents.children == CHILDREN
    assert contents.created_zxid.startswith("0x")
    assert contents.ephemeral_owner is None
    assert [(one.scheme, one.id) for one in contents.acl] == [("world", "anyone")]
    assert contents.acl[0].permissions == ["read", "write", "create", "delete", "admin"]


async def test_an_ephemeral_znode_names_its_session(root: str) -> None:
    path = f"{root}/ephemeral"

    def make_and_read(client: object) -> object:
        client.create(path, b"", ephemeral=True)  # type: ignore[attr-defined]
        return client.client_id[0]  # type: ignore[attr-defined]

    # The session that made it closes with `on_server`, and the znode with it;
    # so it is read through a session kept open for the length of the test.
    from tests.adapters.zookeeper_fixture import raw_client

    client = raw_client()
    try:
        owner = make_and_read(client)
        level = _znodes(await adapter().list_children(root))
        assert level["ephemeral"].ephemeral
        summary = await adapter().node_summary(path)
        assert isinstance(summary.contents, ZnodeContents)
        assert summary.contents.ephemeral_owner == f"0x{owner:x}"
    finally:
        client.stop()
        client.close()


async def test_a_digest_user_reads_what_an_anonymous_session_may_not(root: str) -> None:
    path = f"{root}/secret"
    with pytest.raises(Exception) as refused:
        await adapter().read_content(
            ContentRequest(node_id=path, representation="text")
        )
    assert getattr(refused.value, "error_kind", None) == "auth"
    assert SECRET_USER not in str(refused.value)

    content = await ZookeeperAdapter(digest_options()).read_content(
        ContentRequest(node_id=path, representation="text")
    )
    assert isinstance(content, TextContent) and content.text == "hidden"


async def test_an_unreadable_child_is_listed_by_name_only(root: str) -> None:
    level = _znodes(await adapter().list_children(root))
    secret = level["secret"]
    assert not secret.readable
    assert secret.representations == [] and not secret.summarizable
    assert level["config"].readable

    page = await adapter().fetch(FetchRequest(node_id=root, limit=100))
    names = [row[0] for row in page.rows]
    assert names == sorted(names)
    secret_row = next(row for row in page.rows if row[0] == "secret")
    assert secret_row[1:] == [None] * (len(secret_row) - 1)

    readable = _znodes(await ZookeeperAdapter(digest_options()).list_children(root))
    assert readable["secret"].readable


def test_options_are_the_anonymous_kind_by_default() -> None:
    assert options().auth_method == "anonymous"


async def test_bytes_that_decode_but_hold_control_characters_are_bytes(root: str) -> None:
    # A counter a program stored: valid UTF-8, and not text anyone wrote.
    path = f"{root}/counter"
    await on_server(lambda client: client.create(path, bytes(range(8)) + b"tail"))
    source = adapter()
    editor = await source.read_editor_content(EditorContentRequest(node_id=path))
    assert not editor.writable
    page = await source.fetch(FetchRequest(node_id=root, limit=100))
    counter = next(row for row in page.rows if row[0] == "counter")
    assert counter[1] == "0x" + (bytes(range(8)) + b"tail").hex()
    # A tab and a line break are text.
    await on_server(lambda client: client.set(path, b"a\tb\r\nc"))
    editor = await source.read_editor_content(EditorContentRequest(node_id=path))
    assert editor.writable and editor.text == "a\tb\r\nc"
