"""Open tabs and tab groups, which only the browser knows (S9, D94)."""

import pytest
from httpx import AsyncClient

from app.search.models import MAX_BROWSER_PLACES, MAX_NODE_ID, MAX_NODE_NAME
from tests.utils.search import SEARCH, hits, search

BROWSER = [
    {"object_type": "tab", "object_id": "panel-1", "title": "orders_2024.csv", "detail": "Storage"},
    {"object_type": "tab", "object_id": "panel-2", "title": "Quarterly orders"},
    {"object_type": "tab_group", "object_id": "group-7", "title": "Month end close"},
]


@pytest.mark.parametrize("mode", ["typing", "search"])
async def test_an_open_tab_is_found_by_the_one_word_rule_in_either_mode(
    client: AsyncClient, normal_user_token_headers: dict[str, str], mode: str
) -> None:
    lines = await search(client, normal_user_token_headers, "2024 orders", mode=mode, browser=BROWSER)

    [plan] = [line for line in lines if line["type"] == "plan"]
    [tabs] = [cell for cell in plan["cells"] if cell["key"] == "objects:open_tabs/names"]
    assert tabs["cost"] == "instant"
    assert tabs["group"]["rank"] == min(cell["group"]["rank"] for cell in plan["cells"])
    [found] = hits(lines, "objects:open_tabs")
    assert found["target"] == {"kind": "object", "object_type": "tab", "object_id": "panel-1"}
    assert found["match"]["match_class"] == "word"
    assert found["open"] == "tab"
    assert found["detail"] == "Storage"


async def test_a_tab_group_is_found_and_restores_as_a_group(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    lines = await search(client, normal_user_token_headers, "month end", browser=BROWSER)

    [found] = hits(lines, "objects:open_tabs")
    assert found["target"]["object_type"] == "tab_group"
    assert found["open"] == "tab_group"
    assert found["detail"] == "Tab group"


async def test_what_the_browser_holds_is_bounded(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    too_many = [
        {"object_type": "tab", "object_id": f"panel-{index}", "title": "orders"}
        for index in range(MAX_BROWSER_PLACES + 1)
    ]

    response = await client.post(
        SEARCH,
        headers=normal_user_token_headers,
        json={"words": "orders", "mode": "typing", "browser": too_many},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("length", [250, MAX_NODE_NAME, MAX_NODE_NAME + 500])
async def test_a_long_title_is_cut_rather_than_refusing_the_search(
    client: AsyncClient, normal_user_token_headers: dict[str, str], length: int
) -> None:
    # A panel is titled by its node's name, and a Redis key may be long.
    title = ("quarterly orders " + "x" * length)[:length]
    detail = "Storage · " + "/".join(["folder"] * MAX_NODE_ID)
    browser = [{"object_type": "tab", "object_id": "panel-long", "title": title, "detail": detail}]

    lines = await search(client, normal_user_token_headers, "quarterly orders", mode="typing", browser=browser)

    [found] = hits(lines, "objects:open_tabs")
    assert found["title"] == title[:MAX_NODE_NAME]
    assert found["match"]["match_class"] == "prefix"
    assert found["detail"] == detail[:MAX_NODE_ID]


async def test_no_tab_is_found_when_the_browser_names_none(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    lines = await search(client, normal_user_token_headers, "orders")

    assert hits(lines, "objects:open_tabs") == []


async def test_a_russian_search_names_its_group_and_what_a_hit_is_in_russian(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    russian = {**normal_user_token_headers, "Accept-Language": "ru"}
    lines = await search(client, russian, "month end", browser=BROWSER)

    [plan] = [line for line in lines if line["type"] == "plan"]
    [tabs] = [cell for cell in plan["cells"] if cell["key"] == "objects:open_tabs/names"]
    assert tabs["group"]["title"] == "Открытые вкладки"
    [found] = hits(lines, "objects:open_tabs")
    assert found["detail"] == "Группа вкладок"
