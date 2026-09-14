import uuid

from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import Connector, ConnectorPublic
from tests.utils.user import create_random_user


async def test_connector_is_persisted(db: AsyncSession) -> None:
    user = await create_random_user(db)
    connector = Connector(
        name="local pg",
        adapter_type="postgres",
        config={"host": "localhost", "port": 5432},
        secrets=b"encrypted",
        owner_id=user.id,
    )

    db.add(connector)
    await db.commit()
    await db.refresh(connector)

    assert connector.id is not None
    assert connector.created_at is not None
    assert connector.config["host"] == "localhost"


async def test_duplicate_names_allowed_per_owner(db: AsyncSession) -> None:
    user = await create_random_user(db)
    for _ in range(2):
        db.add(
            Connector(
                name="duplicate",
                adapter_type="postgres",
                config={},
                secrets=b"x",
                owner_id=user.id,
            )
        )

    await db.commit()

    result = await db.exec(
        select(Connector).where(
            Connector.owner_id == user.id, Connector.name == "duplicate"
        )
    )
    assert len(result.all()) == 2


async def test_same_name_allowed_for_different_owners(db: AsyncSession) -> None:
    first = await create_random_user(db)
    second = await create_random_user(db)
    for owner in (first, second):
        db.add(
            Connector(
                name="shared name",
                adapter_type="postgres",
                config={},
                secrets=b"x",
                owner_id=owner.id,
            )
        )

    await db.commit()

    result = await db.exec(select(Connector).where(Connector.name == "shared name"))
    assert len(result.all()) == 2


async def test_connectors_are_deleted_with_owner(db: AsyncSession) -> None:
    user = await create_random_user(db)
    db.add(
        Connector(
            name="to be orphaned",
            adapter_type="postgres",
            config={},
            secrets=b"x",
            owner_id=user.id,
        )
    )
    await db.commit()

    await db.delete(user)
    await db.commit()

    result = await db.exec(select(Connector).where(Connector.owner_id == user.id))
    assert result.all() == []


async def test_a_row_that_names_no_transfer_answer_does_not_allow_it(
    db: AsyncSession,
) -> None:
    """A connection that predates the flag reads as not allowed (D135).

    Written the way rows were written before the column existed, naming none of
    it, so what comes back is the database's default and not the model's.
    """
    user = await create_random_user(db)
    connector_id = uuid.uuid4()
    statement = text(
        "INSERT INTO connector (id, name, adapter_type, config, secrets, owner_id)"
        " VALUES (:id, 'predates the flag', 'postgres', '{}'::jsonb, '\\x00', :owner)"
    ).bindparams(id=connector_id, owner=user.id)
    await db.exec(statement)  # type: ignore[call-overload]
    await db.commit()

    stored = await db.get(Connector, connector_id)

    assert stored is not None
    assert stored.allow_third_party_transfer is False


def test_public_model_has_no_secrets_field() -> None:
    assert "secrets" not in ConnectorPublic.model_fields
