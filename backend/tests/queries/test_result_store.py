"""What the store of captured results keeps, and what it lets go of.

Its own policy, tested without a database: bytes, least recently read, an idle
window, and the one thing it must never drop — a result of a run that is still
happening (D64).
"""

import uuid

from app.adapters.query import MaterialisedResult, ResultColumn
from app.adapters.relation import ColumnType
from app.queries.results import QueryResults

OWNER = uuid.uuid4()


def result(size: int) -> MaterialisedResult:
    return MaterialisedResult(
        columns=[ResultColumn(id="0", name="x", type=ColumnType(sql="text", category="string"))],
        rows=[["x" * size]],
        bytes_used=size,
    )


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test_a_result_comes_back_to_the_person_who_ran_it() -> None:
    store = QueryResults(max_bytes=1000, ttl_seconds=60)
    run_id = uuid.uuid4()

    result_id = await store.put(owner_id=OWNER, run_id=run_id, result=result(10))

    assert result_id is not None
    assert await store.get(result_id, owner_id=OWNER) is not None
    assert await store.get(result_id, owner_id=uuid.uuid4()) is None


async def test_one_result_larger_than_the_whole_store_is_not_kept() -> None:
    store = QueryResults(max_bytes=100, ttl_seconds=60)

    assert await store.put(owner_id=OWNER, run_id=uuid.uuid4(), result=result(200)) is None


async def test_a_result_of_a_run_that_is_still_going_is_never_evicted() -> None:
    store = QueryResults(max_bytes=100, ttl_seconds=60)
    active = uuid.uuid4()
    kept = await store.put(owner_id=OWNER, run_id=active, result=result(80))
    assert kept is not None

    # Nothing evictable, so the new one has to be refused rather than take the
    # place of an answer somebody is still being given.
    crowded = await store.put(owner_id=OWNER, run_id=uuid.uuid4(), result=result(80))

    assert crowded is None
    assert await store.get(kept, owner_id=OWNER) is not None


async def test_a_finished_run_s_result_makes_room_for_a_new_one() -> None:
    store = QueryResults(max_bytes=100, ttl_seconds=60)
    older = uuid.uuid4()
    first = await store.put(owner_id=OWNER, run_id=older, result=result(80))
    assert first is not None
    await store.release(older)

    second = await store.put(owner_id=OWNER, run_id=uuid.uuid4(), result=result(80))

    assert second is not None
    assert await store.get(first, owner_id=OWNER) is None


async def test_the_least_recently_read_result_goes_first() -> None:
    clock = Clock()
    store = QueryResults(max_bytes=100, ttl_seconds=600, clock=clock)
    first_run, second_run = uuid.uuid4(), uuid.uuid4()
    first = await store.put(owner_id=OWNER, run_id=first_run, result=result(40))
    second = await store.put(owner_id=OWNER, run_id=second_run, result=result(40))
    assert first is not None
    assert second is not None
    await store.release(first_run)
    await store.release(second_run)

    clock.now = 10.0
    await store.get(first, owner_id=OWNER)  # first is read, so second is older
    clock.now = 20.0
    third = await store.put(owner_id=OWNER, run_id=uuid.uuid4(), result=result(40))

    assert third is not None
    assert await store.get(first, owner_id=OWNER) is not None
    assert await store.get(second, owner_id=OWNER) is None


async def test_a_result_nobody_read_for_the_idle_window_expires() -> None:
    clock = Clock()
    store = QueryResults(max_bytes=1000, ttl_seconds=60, clock=clock)
    run_id = uuid.uuid4()
    result_id = await store.put(owner_id=OWNER, run_id=run_id, result=result(10))
    assert result_id is not None
    await store.release(run_id)

    clock.now = 61.0

    assert await store.get(result_id, owner_id=OWNER) is None


async def test_reading_a_result_puts_its_idle_window_back() -> None:
    clock = Clock()
    store = QueryResults(max_bytes=1000, ttl_seconds=60, clock=clock)
    run_id = uuid.uuid4()
    result_id = await store.put(owner_id=OWNER, run_id=run_id, result=result(10))
    assert result_id is not None
    await store.release(run_id)

    clock.now = 50.0
    assert await store.get(result_id, owner_id=OWNER) is not None
    clock.now = 100.0

    assert await store.get(result_id, owner_id=OWNER) is not None


async def test_two_results_never_share_an_id() -> None:
    store = QueryResults(max_bytes=10_000, ttl_seconds=60)

    first = await store.put(owner_id=OWNER, run_id=uuid.uuid4(), result=result(10))
    second = await store.put(owner_id=OWNER, run_id=uuid.uuid4(), result=result(10))

    assert first != second
