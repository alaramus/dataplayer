import asyncio
from unittest.mock import AsyncMock, MagicMock

import psycopg
import pytest

from app.adapters.actions import ActionRefused
from app.adapters.postgres.inspection import InspectionReader
from app.adapters.postgres.options import PostgresNoAuth
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError


async def test_inspection_reads_share_one_bounded_read_only_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock()
    connection.execute = AsyncMock()
    cursor = AsyncMock()
    cursor.execute.return_value = cursor
    cursor.fetchall.return_value = [{"value": 1}]
    connection.cursor.return_value = cursor
    session = PostgresSession(PostgresNoAuth(host="localhost", database="fixture", user="reader"))
    acquire = MagicMock()
    acquire.return_value.__aenter__.return_value = connection
    monkeypatch.setattr(session, "_connection", acquire)

    async with session.inspection() as reader:
        assert await reader.query("SELECT 1 AS value", inspection=True) == [{"value": 1}]
        await reader.query("SELECT %s AS value", (2,), inspection=True)

    acquire.assert_called_once_with()
    connection.transaction.assert_called_once_with()
    assert [call.args[0] for call in connection.execute.await_args_list] == [
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
        "SET LOCAL statement_timeout = '5s'",
    ]
    assert [call.args for call in cursor.execute.await_args_list] == [
        ("SELECT 1 AS value", None), ("SELECT %s AS value", (2,)),
    ]


@pytest.mark.parametrize("error", [
    ActionRefused("conflict", "Review again"), asyncio.CancelledError(),
])
async def test_inspection_preserves_refusal_and_cancellation_and_exits_transaction(
    monkeypatch: pytest.MonkeyPatch, error: BaseException,
) -> None:
    connection = MagicMock()
    connection.execute = AsyncMock()
    session = PostgresSession(PostgresNoAuth(host="localhost", database="fixture", user="reader"))
    acquire = MagicMock()
    acquire.return_value.__aenter__.return_value = connection
    monkeypatch.setattr(session, "_connection", acquire)
    with pytest.raises(type(error)):
        async with session.inspection():
            raise error
    assert connection.transaction.return_value.__aexit__.await_args.args[1] is error
    acquire.return_value.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("named", [False, True])
async def test_reader_sanitizes_driver_errors(named: bool) -> None:
    connection = MagicMock()
    cursor = AsyncMock()
    cursor.execute.side_effect = psycopg.errors.InsufficientPrivilege("secret password")
    connection.cursor.return_value = cursor
    reader = InspectionReader(connection)
    with pytest.raises(ValueError if named else AdapterError) as caught:
        await reader.query(
            "SELECT 1", refusals={"42501": "Inspection denied"} if named else None,
            inspection=True,
        )
    assert "secret" not in str(caught.value)
