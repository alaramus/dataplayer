"""Installing and removing an extension, from the report that lists them."""

from collections.abc import AsyncGenerator

import pytest

from app.adapters.actions import ActionRefused, Previews
from app.adapters.fetch import FetchRequest, ScalarFilter
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.system_reports import EXTENSIONS_REPORT_ID, SECTION_ID
from tests.utils.database import working_postgres_options

# Shipped with every PostgreSQL server and installed by nothing here, so it can
# be put on and taken off again without disturbing anything.
SPARE = "pg_trgm"


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


@pytest.fixture(autouse=True)
async def without_the_spare_extension() -> AsyncGenerator[None]:
    """Leave the server exactly as it was found, whichever way a test ends."""
    adapter = _adapter()
    yield
    action = adapter.action("drop_extension")
    try:
        await action.perform(EXTENSIONS_REPORT_ID, {"name": SPARE})
    except (ActionRefused, ValueError):
        pass


async def _available(adapter: PostgresAdapter) -> list[str]:
    return [action.name for action in await adapter.available(EXTENSIONS_REPORT_ID)]


async def test_the_commands_are_offered_on_the_extensions_report() -> None:
    assert sorted(await _available(_adapter())) == [
        "create_extension",
        "drop_extension",
    ]


async def test_no_other_report_offers_them() -> None:
    """`applies_to` says "a report"; which report is a question of state."""
    adapter = _adapter()

    assert await adapter.available(f"{SECTION_ID}.processes") == []
    assert await adapter.available(SECTION_ID) == []


async def test_an_extension_is_installed_and_removed_again() -> None:
    adapter = _adapter()

    created = await adapter.action("create_extension").perform(
        EXTENSIONS_REPORT_ID, {"name": SPARE}
    )
    assert SPARE in created.message
    # The whole connector re-reads: an extension may bring a schema of its own.
    assert created.reload_node_id is None
    assert await _installed(adapter, SPARE) is True

    removed = await adapter.action("drop_extension").perform(
        EXTENSIONS_REPORT_ID, {"name": SPARE}
    )
    assert SPARE in removed.message
    assert await _installed(adapter, SPARE) is False


async def test_a_name_this_server_does_not_offer_is_refused() -> None:
    """The typed text selects a row; it never reaches the statement itself."""
    with pytest.raises(ActionRefused) as refusal:
        await _adapter().action("create_extension").perform(
            EXTENSIONS_REPORT_ID, {"name": 'x"; DROP SCHEMA public CASCADE; --'}
        )

    assert refusal.value.reason == "not_applicable"


async def test_removing_something_that_is_not_installed_is_refused() -> None:
    with pytest.raises(ActionRefused, match="not installed"):
        await _adapter().action("drop_extension").perform(
            EXTENSIONS_REPORT_ID, {"name": SPARE}
        )


async def test_the_commands_refuse_a_node_that_is_not_that_report() -> None:
    with pytest.raises(ActionRefused, match="Extensions report"):
        await _adapter().action("create_extension").perform(
            f"{SECTION_ID}.roles", {"name": SPARE}
        )


async def test_installing_is_previewed_before_it_happens() -> None:
    adapter = _adapter()
    action = adapter.action("create_extension")
    assert isinstance(action, Previews)

    preview = await action.preview(EXTENSIONS_REPORT_ID, {"name": SPARE})

    assert preview.blocked is False
    assert SPARE in preview.summary
    # A rehearsal is rolled back, so asking must not install anything.
    assert await _installed(adapter, SPARE) is False


async def test_removing_is_previewed_and_says_when_nothing_uses_it() -> None:
    adapter = _adapter()
    await adapter.action("create_extension").perform(
        EXTENSIONS_REPORT_ID, {"name": SPARE}
    )

    action = adapter.action("drop_extension")
    assert isinstance(action, Previews)
    preview = await action.preview(EXTENSIONS_REPORT_ID, {"name": SPARE})

    assert preview.blocked is False
    assert SPARE in preview.summary
    # Rolled back: the preview must not have removed it.
    assert await _installed(adapter, SPARE) is True


async def test_removing_never_offers_a_cascade() -> None:
    """A drop reaches whatever anyone built on the extension's types."""
    schema = _adapter().action("drop_extension").params_schema()

    assert "cascade" not in schema.get("properties", {})


async def _installed(adapter: PostgresAdapter, name: str) -> bool:
    result = await adapter.fetch(
        FetchRequest(
            node_id=EXTENSIONS_REPORT_ID,
            limit=5,
            filters=[ScalarFilter(column="name", op="eq", value=name)],
        )
    )
    installed_at = [column.name for column in result.columns].index("installed")
    return result.rows[0][installed_at] == "true"


async def test_installing_one_that_is_already_installed_is_a_conflict() -> None:
    """A taken name is a conflict, the shape a taken folder name already has."""
    adapter = _adapter()
    await adapter.action("create_extension").perform(
        EXTENSIONS_REPORT_ID, {"name": SPARE}
    )

    with pytest.raises(ActionRefused, match="already installed") as refusal:
        await adapter.action("create_extension").perform(
            EXTENSIONS_REPORT_ID, {"name": SPARE}
        )

    assert refusal.value.reason == "conflict"
