import asyncio
import uuid

import pytest

from app.adapters.cache import CacheKey, DataCache, MemoryDataCache
from app.adapters.cache_serialization import CacheFormat

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
