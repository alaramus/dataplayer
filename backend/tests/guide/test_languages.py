"""A page in the request's language, the English where it has none (D227)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.translation import in_language
from app.guide import reader

GUIDE = f"{settings.API_V1_STR}/guide"
ADAPTER_TYPES = f"{settings.API_V1_STR}/adapter-types"


def _clear() -> None:
    reader.pages.cache_clear()
    reader.translated.cache_clear()


@pytest.fixture
def pages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Two English pages and a Russian translation of one, in place of the
    shipped ones — no real page is translated yet."""
    (tmp_path / "connections.md").write_text(
        "# Connections\n\nEnglish\n", encoding="utf-8"
    )
    (tmp_path / "source-postgres.md").write_text(
        "# PostgreSQL\n\n## What you can see\n\n- Tables\n", encoding="utf-8"
    )
    (tmp_path / "ru").mkdir()
    (tmp_path / "ru" / "source-postgres.md").write_text(
        "# PostgreSQL по-русски\n\n## What you can see\n\n- Таблицы\n", encoding="utf-8"
    )
    monkeypatch.setattr(reader, "PAGES_DIR", tmp_path)
    _clear()
    yield tmp_path
    _clear()


@pytest.mark.usefixtures("pages")
def test_a_russian_request_reads_the_russian_page_where_there_is_one() -> None:
    russian = in_language("ru", lambda: reader.page("source-postgres"))
    assert russian is not None
    assert russian.title == "PostgreSQL по-русски"
    untranslated = in_language("ru", lambda: reader.page("connections"))
    assert untranslated is not None
    assert untranslated.title == "Connections"


@pytest.mark.usefixtures("pages")
def test_an_english_request_reads_the_english_page() -> None:
    english = in_language("en", lambda: reader.page("source-postgres"))
    assert english is not None
    assert english.title == "PostgreSQL"


def test_a_translation_english_lacks_is_refused(pages: Path) -> None:
    (pages / "ru" / "nowhere.md").write_text("# Нигде\n", encoding="utf-8")

    with pytest.raises(ValueError, match="nowhere"):
        reader.translated("ru")


@pytest.mark.usefixtures("pages")
async def test_the_routes_answer_in_the_requests_language(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    russian = {**normal_user_token_headers, "Accept-Language": "ru"}

    page = await client.get(f"{GUIDE}/source-postgres", headers=russian)
    assert page.json()["title"] == "PostgreSQL по-русски"
    listed = await client.get(f"{GUIDE}/", headers=russian)
    assert {one["key"]: one["title"] for one in listed.json()} == {
        "connections": "Connections",
        "source-postgres": "PostgreSQL по-русски",
    }
    english = await client.get(
        f"{GUIDE}/source-postgres", headers=normal_user_token_headers
    )
    assert english.json()["title"] == "PostgreSQL"

    types = await client.get(f"{ADAPTER_TYPES}/", headers=russian)
    postgres = next(one for one in types.json() if one["name"] == "postgres")
    assert postgres["can_see"] == ["Таблицы"]
