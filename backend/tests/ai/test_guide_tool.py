"""The agent's `read_guide` tool (D359): the outline, a page and one section."""

import json

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.guide_tool import answer, read_guide, section_text, sections
from app.ai.tools import MAX_RESULT_BYTES
from app.guide import reader
from tests.ai.conftest import (
    Script,
    Turn,
    new_conversation,
    ready_agent,
    send,
    settled,
    text,
)
from tests.ai.test_reading import call, rename, tool_results
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

PAGE = """# Pipelines

What a pipeline is.

## Making one

Press **+**.

### From a template

Pick one.

## Running it

Press **Run**.
"""


def _pages() -> dict[str, reader.GuidePage]:
    return {"pipelines": reader.parse("pipelines", PAGE)}


def test_without_a_key_every_page_is_listed_with_its_sections() -> None:
    assert answer(_pages(), None, None) == {
        "pages": [
            {"key": "pipelines", "title": "Pipelines", "sections": ["Making one", "Running it"]}
        ]
    }


def test_a_key_reads_the_whole_page() -> None:
    assert answer(_pages(), "pipelines", None)["markdown"] == PAGE


def test_a_section_runs_to_the_next_one_and_keeps_its_parts() -> None:
    found = section_text(PAGE, "making ONE")
    assert found == "## Making one\n\nPress **+**.\n\n### From a template\n\nPick one."
    assert section_text(PAGE, "## Running it") == "## Running it\n\nPress **Run**."


def test_an_unknown_page_or_section_says_so_and_what_there_is() -> None:
    assert "error" in answer(_pages(), "nowhere", None)
    missing = answer(_pages(), "pipelines", "Deleting it")
    assert missing["error"] == "This page has no such section."
    assert missing["sections"] == sections(PAGE)


def test_the_shipped_outline_fits_one_result() -> None:
    outline = answer(reader.pages(), None, None)
    assert {"connections", "source-postgres"} <= {one["key"] for one in outline["pages"]}
    assert len(json.dumps(outline, ensure_ascii=False).encode()) < MAX_RESULT_BYTES
    for page in reader.pages().values():
        assert len(page.markdown.encode()) < MAX_RESULT_BYTES, page.key


async def test_the_page_is_in_the_person_s_language() -> None:
    russian = await read_guide("ru", "connections", None)
    assert russian["title"] == reader.translated("ru")["connections"].title
    english = await read_guide("en", "connections", None)
    assert english["title"] == "Connections"


@pytest.fixture
async def headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    person = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    await ready_agent(client, person)
    return person


async def test_the_agent_reads_a_section_of_the_guide(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    script.turns += [
        Turn(tool_calls=[call("read_guide", {}, "c1")]),
        Turn(
            tool_calls=[
                call("read_guide", {"key": "connections", "section": "Adding a connection"}, "c2")
            ]
        ),
        Turn(pieces=[text("Press + at the head of Connections.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "how do I add a connection?")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    assert [step["title"] for step in finished["steps"]] == [
        "Thinking",
        "Reading the guide",
        'Reading "connections" in the guide',
    ]
    outline = tool_results(script, 1)[-1]
    assert any(one["key"] == "connections" for one in outline["pages"])
    section = tool_results(script, 2)[-1]
    assert section["section"].startswith("## Adding a connection")
