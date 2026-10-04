"""Changing the structure of a source through SQL, and what that costs.

D66's third slice: a closed vocabulary, a question asked every time, a
rehearsal that carries a destructive change out and undoes it, and an
invalidation the source issues once the change is permanent.

Against a real PostgreSQL, in a schema each test makes for itself. What a
`DROP ... CASCADE` takes with it is the sort of thing only the database
knows, which is the whole reason the rehearsal exists.
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


async def _postgres(client: AsyncClient, headers: dict[str, str]) -> str:
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
    return str(response.json()["id"])


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
            "confirm_write": True,
            **extra,
        },
    )


async def _change(
    client: AsyncClient, headers: dict[str, str], connector_id: str, text: str
) -> dict[str, Any]:
    """Run one structure change to the end, confirmed as they all must be."""
    started = await _run(
        client,
        headers,
        connector_id,
        text,
        mode="auto_commit",
        confirm_high_risk=True,
    )
    assert started.status_code == 200, started.text
    return await _settled(client, headers, started.json()["id"])


async def _rehearse(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    text: str,
    **extra: Any,
) -> Any:
    return await client.post(
        f"{BASE}/rehearse",
        headers=headers,
        json={"connector_id": connector_id, "text": text, **extra},
    )


async def _table() -> str:
    """A table of this test's own, made outside the query capability."""
    name = f"dp_ddl_{uuid.uuid4().hex[:8]}"
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


async def _exists(
    client: AsyncClient, headers: dict[str, str], connector_id: str, name: str
) -> bool:
    """Whether the source has a relation of this name, asked through a read.

    Bound rather than written into the statement, exactly as a person's own
    parameter would be: the console is the thing under test, so the test uses
    it the way it is meant to be used (D62).
    """
    started = await _run(
        client,
        headers,
        connector_id,
        "select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace"
        " where n.nspname = 'demo_lab' and c.relname = :name",
        parameters=[{"name": "name", "value": name}],
    )
    run = await _settled(client, headers, started.json()["id"])
    page = await client.get(
        f"{BASE}/results/{run['statements'][0]['result_id']}", headers=headers
    )
    return int(page.json()["rows"][0][0]) > 0


# --- the closed vocabulary --------------------------------------------------


async def test_a_table_is_created_and_the_source_says_what_to_re_read(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    name = f"dp_new_{uuid.uuid4().hex[:8]}"

    run = await _change(
        client, headers, connector_id, f"create table demo_lab.{name} (a int)"
    )

    assert run["status"] == "succeeded"
    assert run["write_state"] == "committed"
    # The source names its own nodes; a client never works one out of the SQL.
    assert run["effect"]["reload_node_ids"] == ["demo_lab"]
    assert run["effect"]["relation_node_ids"] == [f"demo_lab.{name}"]
    assert await _exists(client, headers, connector_id, name)


async def test_a_read_run_carries_no_invalidation(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    started = await _run(client, headers, connector_id, "select 1")
    run = await _settled(client, headers, started.json()["id"])

    assert run["effect"] is None


async def test_what_is_outside_the_vocabulary_is_refused_in_the_sources_words(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D66: administering permissions is not a thing a text box may invent."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await _run(
        client,
        headers,
        connector_id,
        "grant select on demo_lab.things to public",
        mode="auto_commit",
        confirm_high_risk=True,
    )

    assert response.status_code == 422
    assert "Permissions" in response.json()["detail"]


async def test_a_maintenance_command_beside_a_change_is_refused_before_anything_is_recorded(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D206: maintenance runs with no transaction, so it shares a run with nothing."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await _run(
        client,
        headers,
        connector_id,
        "create table demo_lab.dp_never (a int); reindex table demo_lab.dp_never",
        mode="auto_commit",
        scope="script",
        confirm_high_risk=True,
    )

    assert response.status_code == 422
    assert "on its own" in response.json()["detail"]


async def test_every_structure_change_is_asked_about_even_a_harmless_one(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    name = f"dp_ask_{uuid.uuid4().hex[:8]}"

    response = await _run(
        client,
        headers,
        connector_id,
        f"create table demo_lab.{name} (a int)",
        mode="auto_commit",
    )

    assert response.status_code == 409
    assert "cannot be undone" in response.json()["detail"]


async def test_a_structure_change_needs_more_than_write_access(
    client: AsyncClient, db: AsyncSession
) -> None:
    """D66: `write` admits DML; the structure needs `structure`."""
    owner_headers = await _headers(client, db)
    writer, writer_headers = await _person(client, db)
    connector_id = await _postgres(client, owner_headers)
    granted = await client.put(
        f"{CONNECTORS}/{connector_id}/grants",
        headers=owner_headers,
        json={"user_id": str(writer.id), "access": "write"},
    )
    assert granted.status_code == 200, granted.text

    response = await _run(
        client,
        writer_headers,
        connector_id,
        "create table demo_lab.dp_never (a int)",
        mode="auto_commit",
        confirm_high_risk=True,
    )

    assert response.status_code == 403
    assert "structure" in response.json()["detail"]


# --- the rehearsal ----------------------------------------------------------


async def test_a_rehearsal_says_what_a_cascade_would_take_and_changes_nothing(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The database's own answer, not a dependency list this project invented."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()
    view = f"dp_view_{uuid.uuid4().hex[:8]}"
    await _change(
        client,
        headers,
        connector_id,
        f"create view demo_lab.{view} as select id from demo_lab.{table}",
    )

    response = await _rehearse(
        client, headers, connector_id, f"drop table demo_lab.{table} cascade"
    )

    assert response.status_code == 200, response.text
    rehearsal = response.json()
    assert rehearsal["runnable"] is True
    assert rehearsal["blocked"] is False
    said = " ".join(
        notice["message"] for notice in rehearsal["statements"][0]["notices"]
    )
    assert view in said
    # And it was undone: the table and its view are both still there.
    assert await _exists(client, headers, connector_id, table)
    assert await _exists(client, headers, connector_id, view)


async def test_a_rehearsal_reports_a_drop_the_source_would_refuse(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()
    view = f"dp_view_{uuid.uuid4().hex[:8]}"
    await _change(
        client,
        headers,
        connector_id,
        f"create view demo_lab.{view} as select id from demo_lab.{table}",
    )

    response = await _rehearse(
        client, headers, connector_id, f"drop table demo_lab.{table}"
    )

    rehearsal = response.json()
    assert rehearsal["runnable"] is False
    assert rehearsal["statements"][0]["outcome"] == "failed"
    assert rehearsal["statements"][0]["diagnostic"] is not None


async def test_a_rehearsal_names_what_would_have_to_be_re_read(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()

    response = await _rehearse(
        client, headers, connector_id, f"drop table demo_lab.{table}"
    )

    assert response.json()["effect"]["reload_node_ids"] == ["demo_lab"]


async def test_a_rehearsal_uses_the_connection_grant_without_an_editor_unlock(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Rehearsing is running: it takes the locks and does the work (D66)."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()

    response = await _rehearse(
        client, headers, connector_id, f"drop table demo_lab.{table}"
    )

    assert response.status_code == 200, response.text
    assert await _exists(client, headers, connector_id, table)


async def test_a_rehearsal_refuses_what_the_vocabulary_refuses(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    response = await _rehearse(
        client, headers, connector_id, "drop database something"
    )

    assert response.status_code == 422
    assert "Databases" in response.json()["detail"]


async def test_a_rehearsal_inside_a_transaction_is_not_blocked_by_that_transaction(
    client: AsyncClient, db: AsyncSession
) -> None:
    """On a second connection this would queue behind the person's own lock.

    Which is why it happens inside the transaction, as a savepoint that is
    rolled back (D66).
    """
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    table = await _table()
    opened = await client.post(
        f"{BASE}/transactions", headers=headers, json={"connector_id": connector_id}
    )
    transaction_id = opened.json()["id"]
    started = await _run(
        client,
        headers,
        connector_id,
        f"update demo_lab.{table} set note = 'held' where id = 1",
        mode="manual",
        transaction_id=transaction_id,
        confirm_high_risk=True,
    )
    await _settled(client, headers, started.json()["id"])

    response = await _rehearse(
        client,
        headers,
        connector_id,
        f"drop table demo_lab.{table}",
        transaction_id=transaction_id,
    )

    assert response.status_code == 200, response.text
    assert response.json()["blocked"] is False
    assert response.json()["runnable"] is True
    # The rehearsal was undone; the transaction's own change is still pending.
    state = await client.get(f"{BASE}/transactions/{transaction_id}", headers=headers)
    assert state.status_code == 200, state.text
    assert state.json()["state"]["broken"] is False
    await client.post(
        f"{BASE}/transactions/{transaction_id}/rollback", headers=headers
    )


# --- when the invalidation is issued ----------------------------------------


async def test_a_committed_transaction_issues_what_its_changes_mean(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    name = f"dp_tx_{uuid.uuid4().hex[:8]}"
    opened = await client.post(
        f"{BASE}/transactions", headers=headers, json={"connector_id": connector_id}
    )
    transaction_id = opened.json()["id"]
    started = await _run(
        client,
        headers,
        connector_id,
        f"create table demo_lab.{name} (a int)",
        mode="manual",
        transaction_id=transaction_id,
        confirm_high_risk=True,
    )
    run = await _settled(client, headers, started.json()["id"])
    # Nothing is issued while it is only pending.
    assert run["write_state"] == "pending"
    assert run["effect"] is None
    open_state = await client.get(
        f"{BASE}/transactions/{transaction_id}", headers=headers
    )
    assert open_state.json()["state"]["ddl_statements"] == 1

    ended = await client.post(
        f"{BASE}/transactions/{transaction_id}/commit", headers=headers
    )

    assert ended.status_code == 200, ended.text
    assert ended.json()["effect"]["relation_node_ids"] == [f"demo_lab.{name}"]
    assert await _exists(client, headers, connector_id, name)


async def test_a_rolled_back_transaction_issues_nothing(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Nothing changed, so telling a client to re-read would be a lie (D66)."""
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)
    name = f"dp_gone_{uuid.uuid4().hex[:8]}"
    opened = await client.post(
        f"{BASE}/transactions", headers=headers, json={"connector_id": connector_id}
    )
    transaction_id = opened.json()["id"]
    started = await _run(
        client,
        headers,
        connector_id,
        f"create table demo_lab.{name} (a int)",
        mode="manual",
        transaction_id=transaction_id,
        confirm_high_risk=True,
    )
    await _settled(client, headers, started.json()["id"])

    ended = await client.post(
        f"{BASE}/transactions/{transaction_id}/rollback", headers=headers
    )

    assert ended.status_code == 200, ended.text
    assert ended.json()["effect"] is None
    assert not await _exists(client, headers, connector_id, name)


async def test_a_structure_change_that_failed_issues_nothing(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _postgres(client, headers)

    run = await _change(
        client, headers, connector_id, "drop table demo_lab.dp_not_there"
    )

    assert run["status"] == "failed"
    assert run["effect"] is None
