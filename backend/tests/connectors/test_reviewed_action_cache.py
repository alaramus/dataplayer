import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.protocol import AdapterError
from app.connectors.routes import _invalidate_after


@pytest.mark.parametrize("error", [
    ActionRefused("conflict", "Review again"), AdapterError("unknown", "Outcome unconfirmed"),
    asyncio.CancelledError(),
])
async def test_reviewed_attempt_invalidates_on_failure_or_cancellation(error: BaseException) -> None:
    cache = AsyncMock()
    connector = uuid.uuid4()
    run = AsyncMock(side_effect=error)
    with pytest.raises(type(error)) as caught:
        await _invalidate_after(run, cache, connector, even_on_failure=True)
    assert caught.value is error
    cache.invalidate_connector.assert_awaited_once_with(connector)


@pytest.mark.parametrize("reviewed", [False, True])
async def test_success_invalidates_once_and_preserves_result(reviewed: bool) -> None:
    cache = AsyncMock()
    connector = uuid.uuid4()
    result = object()
    assert await _invalidate_after(
        AsyncMock(return_value=result), cache, connector, even_on_failure=reviewed,
    ) is result
    cache.invalidate_connector.assert_awaited_once_with(connector)


async def test_ordinary_failed_action_retains_existing_cache_behavior() -> None:
    cache = AsyncMock()
    with pytest.raises(ActionRefused):
        await _invalidate_after(
            AsyncMock(side_effect=ActionRefused("conflict", "Refused")), cache, uuid.uuid4(),
        )
    cache.invalidate_connector.assert_not_awaited()
