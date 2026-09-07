from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError


@pytest.mark.parametrize("fails", [False, True])
async def test_inspection_is_read_only_and_timeout_is_transaction_local(fails: bool) -> None:
    connection = MagicMock()
    connection.execute = AsyncMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock()
    transaction.__aexit__ = AsyncMock(return_value=False)
    connection.transaction.return_value = transaction
    cursor = AsyncMock()
    cursor.fetchall.return_value = [{"value": 1}]
    connection.cursor.return_value.execute = AsyncMock(return_value=cursor)
    if fails:
        connection.cursor.return_value.execute.side_effect = ValueError("secret")

    @asynccontextmanager
    async def acquire():
        yield connection

    session = PostgresSession(
        PostgresUserPassword(host="localhost", user="test", password="test", database="test")
    )
    with patch.object(session, "_connection", acquire):
        if fails:
            with pytest.raises(AdapterError):
                await session.query("SELECT 1", inspection=True)
        else:
            assert await session.query("SELECT 1", inspection=True) == [{"value": 1}]
    assert [call.args[0] for call in connection.execute.await_args_list] == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = '5s'",
    ]
    transaction.__aexit__.assert_awaited_once()
