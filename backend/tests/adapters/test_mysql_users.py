"""Making a MySQL account from the Users report (D243)."""

import uuid
from collections.abc import AsyncIterator

import pytest
from pydantic import SecretStr

from app.adapters.actions import ActionRefused
from app.adapters.fetch import FetchRequest
from app.adapters.mysql import ids
from app.adapters.mysql.adapter import MysqlAdapter
from app.adapters.mysql.options import MysqlUserPassword
from app.adapters.mysql.users import USERS_REPORT_ID
from app.adapters.protocol import AdapterError
from app.adapters.update import InsertRowRequest, InsertValue
from tests.adapters.mysql_fixture import (
    DATABASE,
    TARGETS,
    Target,
    build,
    run,
    tear_down,
)

PASSWORD = "it's a \\ secret"


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    yield chosen
    await tear_down(chosen)


@pytest.fixture
async def account(target: Target) -> AsyncIterator[str]:
    name = f"dp_{uuid.uuid4().hex[:8]}"
    yield name
    await run(target, f"DROP USER IF EXISTS '{name}'@'%'")


def _as(target: Target, name: str, password: str = PASSWORD) -> MysqlAdapter:
    options = target.options(database=DATABASE)
    return MysqlAdapter(
        MysqlUserPassword(
            host=options.host,
            port=options.port,
            user=name,
            password=SecretStr(password),
            database=DATABASE,
        )
    )


async def test_new_user_is_offered_on_the_users_report_alone(target: Target) -> None:
    source = target.adapter(database=DATABASE)

    assert [action.name for action in await source.available(USERS_REPORT_ID)] == ["create_user"]
    assert "create_user" not in [action.name for action in await source.available(ids.database_id(DATABASE))]


async def test_an_account_signs_in_and_reads_nothing(target: Target, account: str) -> None:
    source = target.adapter(database=DATABASE)

    result = await source.action("create_user").perform(
        USERS_REPORT_ID, {"name": account, "password": PASSWORD}
    )

    assert result.message == f"User {account}@% created"
    assert (await _as(target, account).check_connection()).ok is False  # no access to the database
    assert (await MysqlAdapter(
        MysqlUserPassword(
            host=target.options().host,
            port=target.options().port,
            user=account,
            password=SecretStr(PASSWORD),
        )
    ).check_connection()).ok


async def test_an_account_may_be_let_read_the_connection_s_database(
    target: Target, account: str
) -> None:
    source = target.adapter(database=DATABASE)

    await source.action("create_user").perform(
        USERS_REPORT_ID, {"name": account, "password": PASSWORD, "may_read": True}
    )
    reader = _as(target, account)

    page = await reader.fetch(FetchRequest(node_id=ids.relation_id(DATABASE, "items"), limit=1))
    assert page.rows
    with pytest.raises((ValueError, AdapterError)):
        await _write(reader)


async def _write(reader: MysqlAdapter) -> None:
    await reader.insert_row(
        InsertRowRequest(
            node_id=ids.relation_id(DATABASE, "keyless"),
            values=[InsertValue(column="a", value="99")],
        )
    )


async def test_an_account_that_exists_is_a_conflict(target: Target, account: str) -> None:
    source = target.adapter(database=DATABASE)
    create = source.action("create_user")
    await create.perform(USERS_REPORT_ID, {"name": account, "password": PASSWORD})

    with pytest.raises(ActionRefused) as refused:
        await create.perform(USERS_REPORT_ID, {"name": account, "password": PASSWORD})

    assert refused.value.reason == "conflict"


async def test_what_is_not_an_account_is_refused_before_the_server(target: Target) -> None:
    create = target.adapter(database=DATABASE).action("create_user")

    with pytest.raises(ValueError):
        await create.perform(USERS_REPORT_ID, {"name": " padded", "password": PASSWORD})
    with pytest.raises(ValueError):
        await create.perform(USERS_REPORT_ID, {"name": "x" * 33, "password": PASSWORD})
    with pytest.raises(ValueError):
        await create.perform(USERS_REPORT_ID, {"name": "short", "password": "1234"})
    with pytest.raises(ActionRefused):
        await create.perform(ids.database_id(DATABASE), {"name": "elsewhere", "password": PASSWORD})
