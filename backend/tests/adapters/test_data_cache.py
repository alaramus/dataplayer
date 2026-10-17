import asyncio
import uuid
from typing import get_args

import pytest

from app.adapters.cache import (
    CacheArea,
    CacheKey,
    DataCache,
    MemoryDataCache,
    SourceCacheWindows,
    connector_may_choose,
    read_ttl,
)
from app.adapters.cache_serialization import CacheFormat
from app.adapters.protocol import ConnectionCheckResult

TEXT_FORMAT: CacheFormat[str] = CacheFormat(str)


def key(connector_id: uuid.UUID | None = None, request: str = "root") -> CacheKey:
    return CacheKey(
        owner_id=uuid.uuid4(),
        connector_id=connector_id or uuid.uuid4(),
        area="catalog",
        request=request,
    )


async def test_reuses_an_exact_read_until_its_ttl_expires() -> None:
    now = [10.0]
    cache = MemoryDataCache(max_entries=8, clock=lambda: now[0])
    calls = 0

    async def load() -> str:
        nonlocal calls
        calls += 1
        return f"value {calls}"

    cache_key = key()
    first = await cache.get_or_load(
        cache_key, ttl_seconds=5.0, load=load, cache_format=TEXT_FORMAT
    )
    second = await cache.get_or_load(
        cache_key, ttl_seconds=5.0, load=load, cache_format=TEXT_FORMAT
    )
    now[0] = 15.0
    third = await cache.get_or_load(
        cache_key, ttl_seconds=5.0, load=load, cache_format=TEXT_FORMAT
    )

    assert (first.value, first.status) == ("value 1", "miss")
    assert (second.value, second.status) == ("value 1", "hit")
    assert (third.value, third.status) == ("value 2", "miss")
    assert (await cache.health()).measurements.model_dump() == {
        "hits": 1,
        "misses": 2,
        "coalesced": 0,
        "refreshed": 0,
        "bypasses": 0,
        "invalidations": 0,
        "failures": 0,
    }


async def test_refresh_skips_a_live_entry_and_replaces_it() -> None:
    cache = MemoryDataCache(max_entries=8)
    values = iter(["old", "fresh"])

    async def load() -> str:
        return next(values)

    cache_key = key()
    await cache.get_or_load(
        cache_key, ttl_seconds=60.0, load=load, cache_format=TEXT_FORMAT
    )
    refreshed = await cache.get_or_load(
        cache_key,
        ttl_seconds=60.0,
        load=load,
        cache_format=TEXT_FORMAT,
        refresh=True,
    )
    reused = await cache.get_or_load(
        cache_key, ttl_seconds=60.0, load=load, cache_format=TEXT_FORMAT
    )

    assert (refreshed.value, refreshed.status) == ("fresh", "refreshed")
    assert (reused.value, reused.status) == ("fresh", "hit")


async def test_identical_concurrent_reads_share_one_load() -> None:
    cache = MemoryDataCache(max_entries=8)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def load() -> str:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "answer"

    cache_key = key()
    first = asyncio.create_task(
        cache.get_or_load(
            cache_key, ttl_seconds=60.0, load=load, cache_format=TEXT_FORMAT
        )
    )
    await started.wait()
    second = asyncio.create_task(
        cache.get_or_load(
            cache_key, ttl_seconds=60.0, load=load, cache_format=TEXT_FORMAT
        )
    )
    await asyncio.sleep(0)
    release.set()

    results = await asyncio.gather(first, second)
    assert calls == 1
    assert [result.status for result in results] == ["miss", "coalesced"]


async def test_invalidation_during_a_load_prevents_stale_reinsertion() -> None:
    """Forgetting the flight is the whole mechanism, so both halves are asserted.

    A later call must not coalesce with the read begun before the mutation, and
    that read must not store what it returns once it finishes.
    """
    cache = MemoryDataCache(max_entries=8)
    connector_id = uuid.uuid4()
    cache_key = key(connector_id)
    started = asyncio.Event()
    release = asyncio.Event()

    async def old_load() -> str:
        started.set()
        await release.wait()
        return "old"

    loading = asyncio.create_task(
        cache.get_or_load(
            cache_key, ttl_seconds=60.0, load=old_load, cache_format=TEXT_FORMAT
        )
    )
    await started.wait()
    await cache.invalidate_connector(connector_id)

    # Bounded on purpose: were the flight left in place, this call would
    # coalesce with the read still blocked above and the test would hang
    # instead of failing, taking the suite with it.
    async with asyncio.timeout(5):
        fresh = await cache.get_or_load(
            cache_key,
            ttl_seconds=60.0,
            load=lambda: asyncio.sleep(0, result="fresh"),
            cache_format=TEXT_FORMAT,
        )
    assert fresh.value == "fresh"
    assert fresh.status == "miss"

    release.set()
    assert (await loading).value == "old"
    assert await cache.size() == 1
    reused = await cache.get_or_load(
        cache_key,
        ttl_seconds=60.0,
        load=lambda: asyncio.sleep(0, result="wrong"),
        cache_format=TEXT_FORMAT,
    )
    assert reused.value == "fresh"


async def test_evicts_the_least_recently_used_entry_at_the_bound() -> None:
    now = [1.0]
    cache = MemoryDataCache(max_entries=2, clock=lambda: now[0])
    connector_id = uuid.uuid4()
    first = key(connector_id, "first")
    second = key(connector_id, "second")
    third = key(connector_id, "third")

    async def value(name: str) -> str:
        return name

    await cache.get_or_load(
        first,
        ttl_seconds=60.0,
        load=lambda: value("first"),
        cache_format=TEXT_FORMAT,
    )
    now[0] = 2.0
    await cache.get_or_load(
        second,
        ttl_seconds=60.0,
        load=lambda: value("second"),
        cache_format=TEXT_FORMAT,
    )
    now[0] = 3.0
    await cache.get_or_load(
        first,
        ttl_seconds=60.0,
        load=lambda: value("unused"),
        cache_format=TEXT_FORMAT,
    )
    now[0] = 4.0
    await cache.get_or_load(
        third,
        ttl_seconds=60.0,
        load=lambda: value("third"),
        cache_format=TEXT_FORMAT,
    )

    second_again = await cache.get_or_load(
        second,
        ttl_seconds=60.0,
        load=lambda: value("second again"),
        cache_format=TEXT_FORMAT,
    )
    assert second_again.status == "miss"
    assert second_again.value == "second again"


async def test_failed_load_is_not_cached() -> None:
    cache = MemoryDataCache(max_entries=8)
    cache_key = key()

    async def fail() -> str:
        raise RuntimeError("upstream failed")

    with pytest.raises(RuntimeError, match="upstream failed"):
        await cache.get_or_load(
            cache_key, ttl_seconds=60.0, load=fail, cache_format=TEXT_FORMAT
        )

    recovered = await cache.get_or_load(
        cache_key,
        ttl_seconds=60.0,
        load=lambda: asyncio.sleep(0, result="recovered"),
        cache_format=TEXT_FORMAT,
    )
    assert recovered.value == "recovered"
    assert recovered.status == "miss"


def test_memory_cache_implements_the_application_cache_protocol() -> None:
    assert isinstance(MemoryDataCache(max_entries=1), DataCache)


class _Uncacheable:
    """A source that never said its answers may be kept."""

    async def check_connection(self) -> ConnectionCheckResult:
        raise NotImplementedError


class _Cacheable(_Uncacheable):
    """A source with an opinion of its own, in the shape PostgreSQL has."""

    @classmethod
    def cache_ttl(cls, area: CacheArea) -> float:
        if area == "metadata":
            return 300.0
        return 30.0 if area == "catalog" else 10.0


def test_a_source_that_never_opted_in_is_not_cached_by_a_window() -> None:
    # The number in the form says how long, not whether. A driver whose
    # freshness rules nobody wrote down stays read directly (D31).
    assert read_ttl(_Uncacheable(), "catalog", 600) == 0.0
    assert read_ttl(_Uncacheable(), "fetch", None) == 0.0


def test_a_connector_window_replaces_the_source_window_for_what_it_shows() -> None:
    source = _Cacheable()

    assert read_ttl(source, "catalog", 600) == 600.0
    assert read_ttl(source, "fetch", 600) == 600.0
    # Nothing chosen is the source's own answer, which is what every
    # connection made before the column existed still means.
    assert read_ttl(source, "catalog", None) == 30.0
    assert read_ttl(source, "fetch", None) == 10.0


def test_a_connector_window_does_not_reach_editor_metadata() -> None:
    # A whole description of the database, re-read as one unit. Tying it to
    # the window somebody chose for their rows would spend that description
    # on every suggestion list (D105).
    assert read_ttl(_Cacheable(), "metadata", 5) == 300.0
    assert connector_may_choose("metadata") is False


def test_a_window_of_zero_turns_this_connection_off() -> None:
    assert read_ttl(_Cacheable(), "fetch", 0) == 0.0


async def test_a_hit_reports_how_long_ago_the_source_was_read() -> None:
    now = [100.0]
    cache = MemoryDataCache(max_entries=8, clock=lambda: now[0])
    cache_key = key()

    stored = await cache.get_or_load(
        cache_key,
        ttl_seconds=60.0,
        load=lambda: asyncio.sleep(0, result="value"),
        cache_format=TEXT_FORMAT,
    )
    now[0] = 142.0
    reused = await cache.get_or_load(
        cache_key,
        ttl_seconds=60.0,
        load=lambda: asyncio.sleep(0, result="unread"),
        cache_format=TEXT_FORMAT,
    )

    # The read itself is not old. The entry is exactly as old as the time
    # between the two calls, whoever asked and however often.
    assert stored.age_seconds == 0.0
    assert reused.status == "hit"
    assert reused.age_seconds == 42.0


def test_the_windows_a_source_publishes_are_the_ones_it_may_be_re_timed_for() -> None:
    # The form shows these beside the field that replaces them, so the two
    # sets are the same set. A fourth overridable area fails here rather than
    # being offered without ever being described.
    described = set(SourceCacheWindows.model_fields)
    overridable = {
        area for area in get_args(CacheArea) if connector_may_choose(area)
    }

    assert described == overridable


async def test_a_read_in_one_language_is_not_handed_to_another() -> None:
    """What a source writes is worded in the reader's language (D226)."""
    cache = MemoryDataCache(max_entries=8)
    english = key()
    russian = CacheKey(english.owner_id, english.connector_id, english.area, english.request, "ru")

    async def tables() -> str:
        return "Tables"

    async def russian_tables() -> str:
        return "Таблицы"

    first = await cache.get_or_load(english, ttl_seconds=60, load=tables, cache_format=TEXT_FORMAT)
    second = await cache.get_or_load(russian, ttl_seconds=60, load=russian_tables, cache_format=TEXT_FORMAT)

    assert (first.value, second.value) == ("Tables", "Таблицы")
    assert second.status == "miss"
