from unittest.mock import AsyncMock

import pytest

from app.adapters.features import SourceFeature
from app.adapters.postgres.dependencies import MAX_DEPENDENCY_OBJECTS, dependency_scope
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.relation_context import PostgresRelationContext
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.profile import TimescaleProfile
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema


@pytest.mark.parametrize("relation", [None, "customers"])
async def test_scope_follows_view_rules_and_foreign_key_owners(relation: str | None) -> None:
    session = PostgresSession(PostgresUserPassword(**working_postgres_options()))
    async for schema in make_schema():
        scope = await dependency_scope(session, schema, relation)
        assert scope.complete
        assert (schema, "customers") in scope.relations
        assert (schema, "rich_customers") in scope.relations


async def test_dependency_limit_does_not_certify_a_partial_scope() -> None:
    session = AsyncMock()
    session.query.return_value = [
        {"schema_name": "public", "relation_name": "events", "extension_owned": False}
    ] * (MAX_DEPENDENCY_OBJECTS + 1)
    assert not (await dependency_scope(session, "public", None)).complete
    assert session.query.call_args.kwargs["inspection"] is True


@pytest.mark.parametrize("protected", [True, False])
async def test_cascade_classifies_relations_reached_in_another_schema(protected: bool) -> None:
    session = AsyncMock()
    session.query.side_effect = [
        [{"schema_name": "metrics", "relation_name": "hourly", "extension_owned": False}],
        [{"relation_name": "hourly", "specialization": "timescale_continuous_aggregate"}]
        if protected else [],
    ]
    features = AsyncMock()
    features.timescale.return_value = TimescaleProfile(
        SourceFeature(
            code="timescaledb", title="TimescaleDB", state="available",
            installed_version="2.18.0",
        )
    )
    context = PostgresRelationContext(session, features)
    reason = await context.cascade_reason("ordinary", "source")
    assert (reason is not None) == protected
    assert session.query.call_args.args[1] == ("metrics", None)


async def test_extension_owned_function_blocks_schema_cascade() -> None:
    session = AsyncMock()
    session.query.return_value = [
        {"schema_name": None, "relation_name": None, "extension_owned": True}
    ]
    features = AsyncMock()
    features.timescale.return_value = TimescaleProfile(
        SourceFeature(
            code="timescaledb", title="TimescaleDB", state="available",
            installed_version="2.18.0",
        )
    )
    reason = await PostgresRelationContext(session, features).cascade_reason("public", None)
    assert reason == "This cascade affects TimescaleDB extension objects"
