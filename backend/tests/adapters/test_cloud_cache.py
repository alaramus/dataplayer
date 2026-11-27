"""Issued secrets are reused until shortly before they expire, and asked once (D449)."""

import asyncio

import pytest

from app.adapters.cloud import IssuedSecret
from app.adapters.cloud.cache import MARGIN_SECONDS, MAX_KEEP_SECONDS, IssueCache


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


class Issuer:
    def __init__(self, clock: Clock, lifetime: float | None = 900.0) -> None:
        self.clock = clock
        self.lifetime = lifetime
        self.calls = 0

    async def __call__(self) -> IssuedSecret:
        self.calls += 1
        await asyncio.sleep(0)
        expires = None if self.lifetime is None else self.clock.now + self.lifetime
        return IssuedSecret(value=f"token-{self.calls}", expires_at=expires)


async def test_a_secret_is_reused_until_a_minute_before_it_expires() -> None:
    clock = Clock()
    cache = IssueCache(clock)
    issue = Issuer(clock)

    first = await cache.get("account", issue)
    clock.now += 900 - MARGIN_SECONDS - 1
    again = await cache.get("account", issue)
    clock.now += 2
    after = await cache.get("account", issue)

    assert first.value == again.value == "token-1"
    assert after.value == "token-2"
    assert issue.calls == 2


async def test_concurrent_asks_share_one_issue() -> None:
    clock = Clock()
    cache = IssueCache(clock)
    issue = Issuer(clock)

    found = await asyncio.gather(*(cache.get("account", issue) for _ in range(10)))

    assert {one.value for one in found} == {"token-1"}
    assert issue.calls == 1


async def test_a_failure_reaches_every_waiter_and_is_not_kept() -> None:
    cache = IssueCache(Clock())
    calls = 0

    async def refused() -> IssuedSecret:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        raise RuntimeError("denied")

    results = await asyncio.gather(
        *(cache.get("account", refused) for _ in range(3)), return_exceptions=True
    )
    with pytest.raises(RuntimeError):
        await cache.get("account", refused)

    assert all(isinstance(one, RuntimeError) for one in results)
    assert calls == 2


async def test_a_secret_about_to_expire_is_handed_out_once_and_not_kept() -> None:
    clock = Clock()
    cache = IssueCache(clock)
    issue = Issuer(clock, lifetime=MARGIN_SECONDS / 2)

    await cache.get("account", issue)
    await cache.get("account", issue)

    assert issue.calls == 2


async def test_a_secret_that_never_expires_is_read_again_within_minutes() -> None:
    clock = Clock()
    cache = IssueCache(clock)
    issue = Issuer(clock, lifetime=None)

    await cache.get("account", issue)
    clock.now += MAX_KEEP_SECONDS - 1
    await cache.get("account", issue)
    clock.now += 2
    await cache.get("account", issue)

    assert issue.calls == 2


async def test_forgetting_an_account_drops_what_it_issued() -> None:
    clock = Clock()
    cache = IssueCache(clock)
    issue = Issuer(clock)

    await cache.get(("account", 1, "rds"), issue)
    await cache.get(("other", 1, "rds"), issue)
    cache.forget("account")
    await cache.get(("account", 1, "rds"), issue)
    await cache.get(("other", 1, "rds"), issue)

    assert issue.calls == 3


async def test_an_issued_secret_does_not_say_itself() -> None:
    secret = IssuedSecret(value="hunter2", expires_at=None, user="admin")

    assert "hunter2" not in repr(secret)
    assert "admin" not in repr(secret)
