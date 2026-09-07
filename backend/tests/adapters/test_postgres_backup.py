from unittest.mock import AsyncMock

import pytest

from app.adapters.postgres.backup import PostgresBackup
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.protocol import AdapterError


def _backup(session: AsyncMock) -> PostgresBackup:
    return PostgresBackup(
        session,
        PostgresUserPassword(host="localhost", user="test", password="secret", database="test"),
    )


@pytest.mark.parametrize("restore", [False, True])
async def test_timescale_refuses_program_preparation(restore: bool) -> None:
    session = AsyncMock()
    session.query.return_value = [{"extname": "timescaledb"}]
    backup = _backup(session)
    assert not (await backup.backup_availability()).available
    with pytest.raises(ValueError, match="TimescaleDB"):
        if restore:
            await backup.restore_program(from_file="/data/test.dump")
        else:
            await backup.backup_program(into="/data/test.dump")
    assert all(call.args[0] != "SHOW server_version_num" for call in session.query.call_args_list)


async def test_unreadable_extensions_do_not_authorize_backup() -> None:
    session = AsyncMock()
    session.query.side_effect = AdapterError("unknown", "secret driver message")
    offer = await _backup(session).backup_availability()
    assert not offer.available
    assert offer.reason == "Installed extensions could not be inspected for backup or restore"


async def test_plain_postgres_keeps_its_program_and_rechecks_extension_changes() -> None:
    session = AsyncMock()
    session.query.side_effect = [[], [{"server_version_num": "170000"}], [{"extname": "timescaledb"}]]
    backup = _backup(session)
    program = await backup.backup_program(into="/data/test.dump")
    assert program.image == "postgres:17"
    assert program.argv[0] == "pg_dump"
    assert program.environment["PGPASSWORD"] == "secret"
    with pytest.raises(ValueError, match="TimescaleDB"):
        await backup.restore_program(from_file="/data/test.dump")
