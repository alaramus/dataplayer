import asyncio

import pytest

from app.adapters.resources import BorrowingStore, ResourceStore


class Thing:
    """The smallest thing a store can hold: it can be closed, and says so."""

    def __init__(self, name: str = "thing") -> None:
        self.name = name
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class Other:
    async def close(self) -> None:
        pass


def store(*, max_entries: int = 8, max_idle_seconds: float = 300.0) -> ResourceStore:
    return ResourceStore(max_entries=max_entries, max_idle_seconds=max_idle_seconds)


async def test_the_same_key_gives_the_same_object() -> None:
    resources = store()

    first = await resources.get_or_create("a", Thing, lambda: _make("one"))
    again = await resources.get_or_create("a", Thing, lambda: _make("two"))

    assert first is again
    assert first.name == "one"


async def test_a_different_key_gives_a_different_object() -> None:
    resources = store()

    first = await resources.get_or_create("a", Thing, lambda: _make("one"))
    second = await resources.get_or_create("b", Thing, lambda: _make("two"))

    assert first is not second


async def test_concurrent_callers_create_one_object() -> None:
    """Two requests arriving together must not open two pools."""
    resources = store()
    created = 0

    async def slow() -> Thing:
        nonlocal created
        created += 1
        await asyncio.sleep(0.01)
        return Thing()

    made = await asyncio.gather(
        *(resources.get_or_create("a", Thing, slow) for _ in range(5))
    )

    assert created == 1
    assert len({id(thing) for thing in made}) == 1


async def test_a_key_holding_another_kind_is_a_defect_not_a_surprise() -> None:
    resources = store()
    await resources.get_or_create("a", Thing, lambda: _make("one"))

    with pytest.raises(TypeError):
        await resources.get_or_create("a", Other, _make_other)


async def test_the_least_recently_used_goes_when_the_store_is_full() -> None:
    resources = store(max_entries=2)

    first = await resources.get_or_create("a", Thing, lambda: _make("a"))
    await resources.get_or_create("b", Thing, lambda: _make("b"))
    # Touching "a" makes "b" the least recently used one.
    await resources.get_or_create("a", Thing, lambda: _make("a"))
    await resources.get_or_create("c", Thing, lambda: _make("c"))

    assert first.closed is False
    assert await resources.size() == 2


async def test_what_is_evicted_is_closed() -> None:
    resources = store(max_entries=1)

    first = await resources.get_or_create("a", Thing, lambda: _make("a"))
    await resources.get_or_create("b", Thing, lambda: _make("b"))

    assert first.closed is True


async def test_an_entry_left_idle_for_too_long_is_closed() -> None:
    resources = store(max_idle_seconds=0.01)

    stale = await resources.get_or_create("a", Thing, lambda: _make("a"))
    await asyncio.sleep(0.05)
    fresh = await resources.get_or_create("a", Thing, lambda: _make("a again"))

    assert stale.closed is True
    assert fresh is not stale


async def test_closing_the_store_closes_everything_it_holds() -> None:
    resources = store()
    first = await resources.get_or_create("a", Thing, lambda: _make("a"))
    second = await resources.get_or_create("b", Thing, lambda: _make("b"))

    await resources.aclose()

    assert first.closed is True
    assert second.closed is True
    assert await resources.size() == 0


async def test_a_borrowing_store_lends_what_is_there_and_never_closes_it() -> None:
    """A fan-out across connections reuses an open pool and leaves it open (D200)."""
    shared = store()
    theirs = await shared.get_or_create("a", Thing, lambda: _make("theirs"))
    borrowing = BorrowingStore(shared)

    lent = await borrowing.get_or_create("a", Thing, lambda: _make("mine"))
    await borrowing.aclose()

    assert lent is theirs
    assert theirs.closed is False


async def test_what_a_borrowing_store_makes_stays_out_of_the_shared_one() -> None:
    """Made in the shared store, it could push out a pool somebody's grid uses."""
    shared = store(max_entries=1)
    theirs = await shared.get_or_create("a", Thing, lambda: _make("theirs"))
    borrowing = BorrowingStore(shared)

    mine = await borrowing.get_or_create("b", Thing, lambda: _make("mine"))
    await borrowing.aclose()

    assert mine.closed is True
    assert theirs.closed is False
    assert await shared.size() == 1
    assert await shared.existing("b", Thing) is None


async def test_a_borrowing_store_with_nothing_to_borrow_from_makes_its_own() -> None:
    borrowing = BorrowingStore(None)

    mine = await borrowing.get_or_create("a", Thing, lambda: _make("mine"))
    await borrowing.aclose()

    assert mine.closed is True


async def _make(name: str) -> Thing:
    return Thing(name)


async def _make_other() -> Other:
    return Other()
