"""The lab a RabbitMQ started here is filled with (D332)."""

import uuid
from collections.abc import AsyncIterator
from urllib.parse import quote

import httpx
import pytest

from app.adapters.fetch import FetchRequest
from app.adapters.rabbitmq.samples import (
    BILLING,
    BYTES_COUNT,
    CRITICAL,
    DEAD,
    ORDER_COUNT,
    ORDERS,
    SHIPPING,
    TRADE_COUNT,
    TRADES,
)
from tests.adapters.rabbitmq_fixture import adapter, management, options, password, user


@pytest.fixture(scope="module")
async def vhost() -> AsyncIterator[str]:
    """An empty virtual host, as a broker started here has."""
    made = f"dp lab/{uuid.uuid4().hex[:12]}"
    segment = quote(made, safe="")
    async with httpx.AsyncClient(
        base_url=management() + "/api", auth=(user(), password())
    ) as api:
        (await api.put(f"/vhosts/{segment}")).raise_for_status()
        (
            await api.put(
                f"/permissions/{segment}/{quote(user(), safe='')}",
                json={"configure": ".*", "write": ".*", "read": ".*"},
            )
        ).raise_for_status()
        yield made
        await api.delete(f"/vhosts/{segment}")


async def test_the_lab_fills_an_empty_broker(vhost: str) -> None:
    lab = adapter(options(vhost))
    said = await lab.install_sample_data()
    assert TRADES in said
    v = quote(vhost, safe="")

    queues = {node.name for node in await lab.list_children(f"queues:{v}")}
    assert queues == {BILLING, SHIPPING, DEAD, CRITICAL}
    exchanges = [node.name for node in await lab.list_children(f"exchanges:{v}")]
    assert exchanges[:3] == ["lab.alerts", "lab.dead-letter", ORDERS]

    session = lab._session  # noqa: SLF001 - the exact count, not the API's sample
    paid = sum(1 for index in range(ORDER_COUNT) if index % 5 != 0)
    assert await session.waiting(vhost, BILLING) == ORDER_COUNT
    assert await session.waiting(vhost, SHIPPING) == paid
    assert await session.waiting(vhost, CRITICAL) == 4
    assert await session.waiting(vhost, DEAD) == 0

    page = await lab.fetch(
        FetchRequest(node_id=f"stream:{v}/{quote(TRADES, safe='')}", limit=10)
    )
    names = [column.name for column in page.columns]
    assert "body.symbol" in names
    # The newest are the sensor's raw readings, shown in hex.
    assert all((row[7] or "").startswith("0x") for row in page.rows[:BYTES_COUNT])
    assert page.rows[BYTES_COUNT][0] == str(TRADE_COUNT - 1)
