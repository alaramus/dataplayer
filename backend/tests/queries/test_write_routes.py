"""Changing data through SQL, and everything that stands in front of it.

D66/D160: the owner's policy, the grant, and a question asked every time
about what cannot be undone. Against a real PostgreSQL, on a table these tests
create for themselves, because what a transaction does is only true of a real
one.
"""

import asyncio
import uuid
from typing import Any

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud as user_crud
from app.users.models import User
from tests.utils.database import working_postgres_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/queries"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


async def _headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )


async def _person(client: AsyncClient, db: AsyncSession) -> tuple[User, dict[str, str]]:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await user_crud.get_user_by_email(session=db, email=email)
    assert user is not None
    return user, headers


async def _postgres(
    client: AsyncClient, headers: dict[str, str], policy: str | None = "allow_writes"
) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"pg {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200, response.text
    connector_id = str(response.json()["id"])
    if policy is not None:
        changed = await client.patch(
            f"{CONNECTORS}/{connector_id}",
            headers=headers,
            json={"execution_policy": policy},
        )
        assert changed.status_code == 200, changed.text
    return connector_id


async def _settled(
    client: AsyncClient, headers: dict[str, str], run_id: str, *, seconds: float = 15.0
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + seconds
    while True:
        response = await client.get(f"{BASE}/runs/{run_id}", headers=headers)
        assert response.status_code == 200, response.text
        run: dict[str, Any] = response.json()
        if run["status"] not in {"accepted", "running", "cancelling"}:
            return run
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"The run never settled: {run['status']}")
        await asyncio.sleep(0.05)


async def _run(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    text: str,
    **extra: Any,
) -> Any:
    return await client.post(
        f"{BASE}/runs",
        headers=headers,
        json={
            "run_id": str(uuid.uuid4()),
            "connector_id": connector_id,
            "text": text,
            **extra,
        },
    )


async def _table() -> str:
    """A table of this test's own, made outside the query capability.

    Through a read connection's own DDL is not offered, so the fixture is built
    the way the rest of the application builds one: it is not what is under
    test here.
    """
    name = f"dp_write_{uuid.uuid4().hex[:8]}"
    from app.adapters.postgres.options import PostgresUserPassword
    from app.adapters.postgres.session import PostgresSession

    session = PostgresSession(PostgresUserPassword(**working_postgres_options()))
    async with session.acquire() as connection:
        await connection.execute(
            f"CREATE TABLE demo_lab.{name} (id int primary key, note text)"
        )
        await connection.execute(f"INSERT INTO demo_lab.{name} VALUES (1, 'one')")
        await connection.commit()
    return name


async def _rows(
    client: AsyncClient, headers: dict[str, str], connector_id: str, table: str
) -> int:
    started = await _run(
        client, headers, connector_id, f"select count(*) from demo_lab.{table}"
    )
    run = await _settled(client, headers, started.json()["id"])
    result_id = run["statements"][0]["result_id"]
    page = await client.get(f"{BASE}/results/{result_id}", headers=headers)
    return int(page.json()["rows"][0][0])


# --- the connection's execution policy -------------------------------------


async def test_a_connection_asks_for_confirmation_by_default(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers, policy=None)
    table = await _table()
    statement = f"update demo_lab.{table} set note = 'confirmed' where id = 1"

    refused = await _run(client, headers, connector_id, statement, mode="auto_commit")
    accepted = await _run(
        client, headers, connector_id, statement,
        mode="auto_commit", confirm_write=True,
    )

    assert refused.status_code == 409
    assert "Confirm this write" in refused.json()["detail"]
    assert accepted.status_code == 200, accepted.text
    run = await _settled(client, headers, accepted.json()["id"])
    assert run["status"] == "succeeded"


async def test_a_connection_its_owner_keeps_read_only_blocks_writes(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers, policy="read_only")
    table = await _table()

    response = await _run(
        client, headers, connector_id,
        f"update demo_lab.{table} set note = 'x' where id = 1",
        mode="auto_commit", confirm_write=True,
    )

    assert response.status_code == 403
    assert "reading only" in response.json()["detail"]


async def test_allowing_writes_needs_no_editor_unlock(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers, policy="allow_writes")
    table = await _table()

    response = await _run(
        client, headers, connector_id,
        f"update demo_lab.{table} set note = 'allowed' where id = 1",
        mode="auto_commit",
    )

    assert response.status_code == 200, response.text
    run = await _settled(client, headers, response.json()["id"])
    assert run["status"] == "succeeded"


async def test_a_reader_cannot_write_what_they_may_only_read(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner_headers = await _headers(client, db)
    reader, reader_headers = await _person(client, db)
    connector_id = await _postgres(client, owner_headers, policy="allow_writes")
    granted = await client.put(
        f"{CONNECTORS}/{connector_id}/grants",
        headers=owner_headers,
        json={"user_id": str(reader.id), "access": "read"},
    )
    assert granted.status_code == 200, granted.text

    table = await _table()
    response = await _run(
        client, reader_headers, connector_id,
        f"update demo_lab.{table} set note = 'x' where id = 1",
        mode="auto_commit",
    )

    assert response.status_code == 403
    assert "write access" in response.json()["detail"]


# --- what a run may do ------------------------------------------------------


async def test_a_change_is_refused_while_the_document_is_read_only(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()

    response = await _run(
        client,
        headers,
        connector_id,
        f"update demo_lab.{table} set note = 'x' where id = 1",
    )

    assert response.status_code == 422
    assert "read" in response.json()["detail"]


async def test_an_auto_commit_change_is_made_and_kept(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()

    started = await _run(
        client,
        headers,
        connector_id,
        f"insert into demo_lab.{table} values (2, 'two')",
        mode="auto_commit",
    )
    assert started.status_code == 200, started.text
    run = await _settled(client, headers, started.json()["id"])

    assert run["status"] == "succeeded"
    assert run["write_state"] == "committed"
    assert run["statements"][0]["affected_rows"] == 1
    assert run["statements"][0]["command_tag"] == "INSERT 0 1"
    assert await _rows(client, headers, connector_id, table) == 2


async def test_an_auto_commit_script_that_fails_keeps_nothing(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D66: the complete run is one transaction, committed only if it all worked."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()

    started = await _run(
        client,
        headers,
        connector_id,
        f"insert into demo_lab.{table} values (3, 'three'); "
        f"insert into demo_lab.{table} values (3, 'again')",
        mode="auto_commit",
        scope="script",
        confirm_high_risk=True,
    )
    run = await _settled(client, headers, started.json()["id"])

    assert run["status"] == "failed"
    assert run["write_state"] == "rolled_back"
    # The first insert succeeded and was undone with the second one's failure.
    assert await _rows(client, headers, connector_id, table) == 1


async def test_something_that_cannot_be_undone_is_asked_about_every_time(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()

    unconfirmed = await _run(
        client,
        headers,
        connector_id,
        f"delete from demo_lab.{table}",
        mode="auto_commit",
    )
    confirmed = await _run(
        client,
        headers,
        connector_id,
        f"delete from demo_lab.{table}",
        mode="auto_commit",
        confirm_high_risk=True,
    )

    assert unconfirmed.status_code == 409
    assert "cannot be undone" in unconfirmed.json()["detail"]
    assert confirmed.status_code == 200, confirmed.text
    run = await _settled(client, headers, confirmed.json()["id"])
    assert run["status"] == "succeeded"
    assert await _rows(client, headers, connector_id, table) == 0




async def test_a_writer_without_the_level_is_refused_by_the_level(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner_headers = await _headers(client, db)
    reader, reader_headers = await _person(client, db)
    connector_id = await _postgres(client, owner_headers, policy="allow_writes")
    table = await _table()
    await client.put(
        f"{CONNECTORS}/{connector_id}/grants",
        headers=owner_headers,
        json={"user_id": str(reader.id), "access": "read"},
    )

    response = await _run(
        client,
        reader_headers,
        connector_id,
        f"update demo_lab.{table} set note = 'x' where id = 1",
        mode="auto_commit",
    )

    assert response.status_code in (403, 409)


# --- a transaction somebody holds -------------------------------------------


async def _open(client: AsyncClient, headers: dict[str, str], connector_id: str) -> Any:
    return await client.post(
        f"{BASE}/transactions", headers=headers, json={"connector_id": connector_id}
    )


async def test_a_manual_transaction_holds_changes_until_it_is_committed(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    watcher = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()
    opened = await _open(client, headers, connector_id)
    assert opened.status_code == 200, opened.text
    transaction_id = opened.json()["id"]

    started = await _run(
        client,
        headers,
        connector_id,
        f"insert into demo_lab.{table} values (4, 'four')",
        mode="manual",
        transaction_id=transaction_id,
    )
    run = await _settled(client, headers, started.json()["id"])

    assert run["status"] == "succeeded"
    assert run["write_state"] == "pending"
    state = await client.get(f"{BASE}/transactions/{transaction_id}", headers=headers)
    assert state.json()["state"]["mutating_statements"] == 1
    assert state.json()["state"]["affected_rows"] == 1
    assert state.json()["age_seconds"] >= 0

    committed = await client.post(
        f"{BASE}/transactions/{transaction_id}/commit", headers=headers
    )

    assert committed.status_code == 200, committed.text
    assert "1 rows" in committed.json()["message"]
    settled = await client.get(f"{BASE}/runs/{run['id']}", headers=headers)
    assert settled.json()["write_state"] == "committed"
    assert await _rows(client, headers, connector_id, table) == 2
    assert watcher is not None


async def test_rolling_back_undoes_what_succeeded(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()
    transaction_id = (await _open(client, headers, connector_id)).json()["id"]
    started = await _run(
        client,
        headers,
        connector_id,
        f"insert into demo_lab.{table} values (5, 'five')",
        mode="manual",
        transaction_id=transaction_id,
    )
    run = await _settled(client, headers, started.json()["id"])

    rolled = await client.post(
        f"{BASE}/transactions/{transaction_id}/rollback", headers=headers
    )

    assert rolled.status_code == 200, rolled.text
    settled = await client.get(f"{BASE}/runs/{run['id']}", headers=headers)
    assert settled.json()["write_state"] == "rolled_back"
    assert await _rows(client, headers, connector_id, table) == 1


async def test_a_failed_statement_leaves_a_transaction_that_can_only_be_rolled_back(
    client: AsyncClient, db: AsyncSession
) -> None:
    """PostgreSQL makes it unusable, and the answer says so rather than trying."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()
    transaction_id = (await _open(client, headers, connector_id)).json()["id"]
    started = await _run(
        client,
        headers,
        connector_id,
        f"insert into demo_lab.{table} values (1, 'clash')",
        mode="manual",
        transaction_id=transaction_id,
    )
    await _settled(client, headers, started.json()["id"])

    state = await client.get(f"{BASE}/transactions/{transaction_id}", headers=headers)
    commit = await client.post(
        f"{BASE}/transactions/{transaction_id}/commit", headers=headers
    )
    another = await _run(
        client,
        headers,
        connector_id,
        f"insert into demo_lab.{table} values (6, 'six')",
        mode="manual",
        transaction_id=transaction_id,
    )

    assert state.json()["state"]["broken"] is True
    assert commit.status_code == 409
    assert another.status_code == 409
    await client.post(f"{BASE}/transactions/{transaction_id}/rollback", headers=headers)


async def test_a_transaction_belonging_to_somebody_else_does_not_exist(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    stranger = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    transaction_id = (await _open(client, headers, connector_id)).json()["id"]

    read = await client.get(f"{BASE}/transactions/{transaction_id}", headers=stranger)
    committed = await client.post(
        f"{BASE}/transactions/{transaction_id}/commit", headers=stranger
    )

    assert read.status_code == 404
    assert committed.status_code == 404
    await client.post(f"{BASE}/transactions/{transaction_id}/rollback", headers=headers)


async def test_opening_a_transaction_uses_the_connection_policy_and_grant(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    read_only = await _postgres(client, headers, policy="read_only")

    allowed = await _open(client, headers, connector_id)
    blocked = await _open(client, headers, read_only)

    assert allowed.status_code == 200, allowed.text
    assert blocked.status_code == 403
    await client.post(
        f"{BASE}/transactions/{allowed.json()['id']}/rollback", headers=headers
    )


async def test_a_manual_run_needs_a_transaction_that_is_open(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()

    without = await _run(
        client,
        headers,
        connector_id,
        f"update demo_lab.{table} set note = 'x' where id = 1",
        mode="manual",
    )
    gone = await _run(
        client,
        headers,
        connector_id,
        f"update demo_lab.{table} set note = 'x' where id = 1",
        mode="manual",
        transaction_id="no-such-transaction",
    )

    assert without.status_code == 422
    assert gone.status_code == 404


async def test_an_idle_transaction_is_rolled_back_by_its_lease(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D66: five minutes in the application, and a moment here."""
    from app.main import app

    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()
    transaction_id = (await _open(client, headers, connector_id)).json()["id"]
    started = await _run(
        client,
        headers,
        connector_id,
        f"insert into demo_lab.{table} values (7, 'seven')",
        mode="manual",
        transaction_id=transaction_id,
    )
    await _settled(client, headers, started.json()["id"])

    sessions = app.state.query_sessions
    ended = await sessions.sweep(now=_far_future())

    assert ended == 1
    assert (
        await client.get(f"{BASE}/transactions/{transaction_id}", headers=headers)
    ).status_code == 404
    assert await _rows(client, headers, connector_id, table) == 1


def _far_future() -> Any:
    from datetime import UTC, datetime, timedelta

    return datetime.now(UTC) + timedelta(hours=1)
