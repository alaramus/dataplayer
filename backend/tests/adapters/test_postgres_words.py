"""PostgreSQL answers in the language of the request (D226)."""

import uuid

import pytest

from app.adapters.actions import ActionRefused, Previews, TakesParams
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.column_types import POSTGRES_COLUMN_TYPE_OPTIONS
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.words import worded_titles
from app.core.translation import current_language, in_language
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import run


def adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


def test_a_vocabulary_is_handed_out_worded_and_kept_in_english() -> None:
    worded = in_language("ru", lambda: worded_titles(POSTGRES_COLUMN_TYPE_OPTIONS))

    assert worded[0].title == "Текст"
    assert worded[0].code == "text", "a code is data and stays as it is"
    assert POSTGRES_COLUMN_TYPE_OPTIONS[0].title == "Text"


async def test_a_refusal_and_a_preview_are_written_in_russian() -> None:
    source = adapter()
    name = f"words_{uuid.uuid4().hex}"
    await run(f'CREATE SCHEMA "{name}"')  # noqa: S608 -- generated test schema.
    # Set here rather than in a fixture: the event loop runs the test in a
    # context of its own, which a fixture's setting would not reach.
    token = current_language.set("ru")
    try:
        create = source.action("create_schema")
        assert isinstance(create, TakesParams)
        with pytest.raises(ActionRefused) as refused:
            await create.perform(None, {"name": name})

        drop = source.action("drop_schema")
        assert isinstance(drop, Previews)
        preview = await drop.preview(name, {"cascade": False})

        assert refused.value.message == f"Схема «{name}» уже существует"
        assert preview.summary == f"Схема {name} пуста"
    finally:
        current_language.reset(token)
        await run(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')  # noqa: S608 -- generated test schema.
