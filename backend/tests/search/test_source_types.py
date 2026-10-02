"""Source types, found by what the type catalog shows of them (S1).

The catalog window keeps no rule of its own any more: these are the cases its
own matching was tested for, asked of the provider instead.
"""

import uuid

from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.search import SearchBounds, words_of
from app.search.providers import Asked
from app.search.source_types import SourceTypes, Startable
from app.users.models import User

# A service no page and no description mentions, so only the template can
# find its type. TimescaleDB itself is named in PostgreSQL's guide page.
QUOKKA = Startable(
    adapter_type="postgres",
    title="QuokkaDB",
    description="A PostgreSQL server with an extension nobody has heard of.",
)


def _asked(db: AsyncSession, typed: str) -> Asked:
    return Asked(
        user=User(id=uuid.uuid4(), email="nobody@example.com", hashed_password="x"),
        typed=typed,
        words=words_of(typed),
        field="names",
        mode="typing",
        limit=50,
        bounds=SearchBounds.within(5),
        session=db,
    )


async def _found(db: AsyncSession, typed: str, *startable: Startable) -> list[str]:
    provider = SourceTypes(lambda: list(startable))
    found = await provider.search(_asked(db, typed))
    return [hit.target.object_id for hit in found.hits if hit.target.kind == "object"]


async def test_a_type_is_found_by_its_title_first(db: AsyncSession) -> None:
    assert (await _found(db, "postgre"))[0] == "postgres"


async def test_a_type_is_found_by_its_category(db: AsyncSession) -> None:
    assert "file" in await _found(db, "storage")


async def test_a_title_match_stands_above_a_match_in_what_it_says(db: AsyncSession) -> None:
    found = await _found(db, "redis")

    assert found[0] == "redis"


async def test_a_type_is_found_by_what_this_server_can_start_of_it(db: AsyncSession) -> None:
    """A service is a type here (D119): looking for it by name finds where it starts."""
    assert await _found(db, "quokkadb") == []
    assert await _found(db, "quokkadb", QUOKKA) == ["postgres"]


async def test_a_template_of_another_kind_does_not_offer_this_one(db: AsyncSession) -> None:
    elsewhere = Startable(adapter_type="file", title="QuokkaDB", description="")

    assert await _found(db, "quokkadb", elsewhere) == ["file"]


async def test_nothing_matching_finds_nothing(db: AsyncSession) -> None:
    assert await _found(db, "kafka") == []
