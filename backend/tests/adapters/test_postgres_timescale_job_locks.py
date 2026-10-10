from unittest.mock import AsyncMock, MagicMock

from psycopg import sql

from app.adapters.postgres.timescale import job_locks


def source_connection(restore: str, shorter: int) -> MagicMock:
    connection = MagicMock()
    connection.execute = AsyncMock()
    cursor = MagicMock()
    cursor.fetchone = AsyncMock(return_value={"restore": restore, "shorter": shorter})
    connection.cursor.return_value.execute = AsyncMock(return_value=cursor)
    return connection


async def test_removals_run_as_one_statement_under_a_shorter_wait_then_restore_it() -> None:
    connection = source_connection("2s", 333)
    calls = [sql.SQL("{}(%s)").format(sql.Identifier("ext", name)) for name in ("remove_a", "remove_b")]
    await job_locks.remove_jobs(connection, calls, ["123", "123"])
    statements = connection.execute.await_args_list
    assert statements[0].args[0].as_string() == "SET LOCAL lock_timeout = '333ms'"
    assert (statements[1].args[0].as_string(), statements[1].args[1]) == (
        'SELECT "ext"."remove_a"(%s), "ext"."remove_b"(%s)', ("123", "123"),
    )
    assert statements[2].args == ("SELECT pg_catalog.set_config('lock_timeout', %s, true)", ("2s",))
    assert len(statements) == 3

