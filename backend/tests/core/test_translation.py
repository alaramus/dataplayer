"""Words a source writes, worded in the language a request asks for (D226)."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import translation
from app.core.translation import (
    RequestLanguage,
    in_language,
    register,
    requested_language,
    say,
    say_schema,
)

register("ru", {"Drop table": "Удалить таблицу", "Drop {name}?": "Удалить {name}?"})


def test_the_language_asked_for_is_the_first_one_spoken() -> None:
    assert requested_language("de-DE,ru;q=0.8,en;q=0.5", None) == "de"
    assert requested_language("ru,de;q=0.8,en;q=0.5", None) == "ru"
    assert requested_language("RU", None) == "ru"
    assert requested_language("ja", None) == "en"
    assert requested_language(None, None) == "en"
    # A socket cannot carry the header, so its query names it, and wins.
    assert requested_language("en-US", "ru") == "ru"
    assert requested_language("ru", "tlh") == "ru"


def test_english_is_the_key_and_what_a_language_lacks_stays_english() -> None:
    assert in_language("ru", lambda: say("Drop table")) == "Удалить таблицу"
    assert in_language("en", lambda: say("Drop table")) == "Drop table"
    assert in_language("ru", lambda: say("Never translated")) == "Never translated"


def test_parameters_fill_the_translated_sentence_and_stay_as_they_are() -> None:
    assert in_language("ru", lambda: say("Drop {name}?", name="orders")) == "Удалить orders?"


def test_a_schema_has_its_words_translated_and_its_data_left_alone() -> None:
    schema = {
        "title": "Drop table",
        "properties": {
            "Drop table": {"title": "Drop table", "default": "Drop table"},
            "kind": {
                "enum": ["Drop table"],
                "x-ui-choices": [{"value": "Drop table", "label": "Drop table"}],
            },
        },
    }

    worded = in_language("ru", lambda: say_schema(schema))

    assert worded["title"] == "Удалить таблицу"
    # A property's name is an identifier, a default and an enum are data.
    assert list(worded["properties"]) == ["Drop table", "kind"]
    assert worded["properties"]["Drop table"]["title"] == "Удалить таблицу"
    assert worded["properties"]["Drop table"]["default"] == "Drop table"
    assert worded["properties"]["kind"]["enum"] == ["Drop table"]
    assert worded["properties"]["kind"]["x-ui-choices"] == [
        {"value": "Drop table", "label": "Удалить таблицу"}
    ]
    assert schema["title"] == "Drop table", "the original is not changed"


async def test_a_request_is_answered_in_the_language_it_asks_for() -> None:
    application = FastAPI()

    @application.get("/title")
    async def title() -> dict[str, str]:
        return {"title": say("Drop table")}

    asgi = RequestLanguage(application)
    async with AsyncClient(transport=ASGITransport(app=asgi), base_url="http://test") as client:
        russian = await client.get("/title", headers={"Accept-Language": "ru-RU,ru"})
        english = await client.get("/title")
        by_query = await client.get("/title?lang=ru")

    assert russian.json() == {"title": "Удалить таблицу"}
    assert english.json() == {"title": "Drop table"}
    assert by_query.json() == {"title": "Удалить таблицу"}
    assert translation.current_language.get() == "en", "nothing leaks out of a request"
