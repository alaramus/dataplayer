from unittest.mock import AsyncMock

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.catalog import SchemaNode, TableNode
from app.adapters.postgres.actions import (
    DescribeModel,
    DropRelation,
    DropSchema,
    MoveRelation,
    PostgresActions,
    RenameRelation,
    RenameSchema,
)
from app.adapters.postgres.row_commands import PostgresRowCommands
from app.adapters.postgres.system_reports import EXTENSIONS_REPORT_ID


def _catalog(reason: str | None) -> AsyncMock:
    catalog = AsyncMock()
    catalog.path_to.return_value = [
        SchemaNode(id="public", name="public", has_children=True, representations=[]),
        TableNode(id="public.events", name="events", has_children=False, representations=[]),
    ]
    catalog.relation_action_reason.return_value = reason
    catalog.schema_action_reason.return_value = None
    catalog.cascade_reason.return_value = None
    return catalog


@pytest.mark.parametrize(
    "reason",
    [
        "TimescaleDB relations are read-only in this version",
        "TimescaleDB relation status could not be established",
    ],
)
async def test_protected_or_unknown_relation_has_no_registered_actions(
    reason: str,
) -> None:
    catalog = _catalog(reason)
    assert await PostgresActions(AsyncMock(), catalog).available("public.events") == []
    catalog.relation_action_reason.assert_awaited_once_with("public", "events")


async def test_ordinary_relation_keeps_registered_actions() -> None:
    actions = await PostgresActions(AsyncMock(), _catalog(None)).available(
        "public.events"
    )
    assert {action.name for action in actions} == {
        "rename_relation", "move_relation", "drop_relation", "describe_model"
    }


async def test_action_offers_keep_the_guard_reason_without_repeating_discovery() -> None:
    reason = "TimescaleDB relation status could not be established"
    catalog = _catalog(reason)
    offers = await PostgresActions(AsyncMock(), catalog).action_offers("public.events")
    assert not offers.actions
    assert {item.name for item in offers.refusals} == {
        "rename_relation", "move_relation", "drop_relation", "describe_model",
    }
    assert all(item.reason == reason for item in offers.refusals)
    catalog.relation_action_reason.assert_awaited_once_with("public", "events")
    assert offers.reason_for("create_schema") is None


async def test_direct_relation_actions_refuse_before_sql_or_model_reads() -> None:
    session = AsyncMock()
    catalog = _catalog("TimescaleDB relations are read-only in this version")
    with pytest.raises(ActionRefused, match="TimescaleDB"):
        await RenameRelation(session, catalog).perform(
            "public.events", {"new_name": "renamed"}
        )
    with pytest.raises(ActionRefused, match="TimescaleDB"):
        await MoveRelation(session, catalog).perform(
            "public.events", {"target_schema": "archive"}
        )
    with pytest.raises(ActionRefused, match="TimescaleDB"):
        await DescribeModel(session, catalog).download(["public.events"], {})
    session.query.assert_not_awaited()
    session.schema_change.assert_not_awaited()


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("as_set", [False, True])
async def test_drop_guard_covers_execution_preview_and_sets(
    preview: bool, as_set: bool,
) -> None:
    session = AsyncMock()
    action = DropRelation(session, _catalog("TimescaleDB status is unknown"))
    with pytest.raises(ActionRefused, match="TimescaleDB"):
        if as_set:
            operation = action.preview_on_set if preview else action.perform_on_set
            await operation(["public.events"], {"cascade": True})
        elif preview:
            await action.preview("public.events", {"cascade": True})
        else:
            await action.perform("public.events", {"cascade": True})
    session.transaction.assert_not_called()
    session.rehearse.assert_not_awaited()


async def test_extension_row_command_cannot_remove_timescale() -> None:
    session = AsyncMock()
    session.query.return_value = [{"name": "timescaledb"}]
    result = await PostgresRowCommands(session).run(
        EXTENSIONS_REPORT_ID, "drop_extension", ["timescaledb"]
    )
    assert result.done == 0
    assert result.refused == [
        "TimescaleDB removal is not supported by structured operations"
    ]
    session.schema_change.assert_not_awaited()


async def test_schema_model_export_refuses_a_protected_member() -> None:
    catalog = _catalog("TimescaleDB relations are read-only in this version")
    catalog.path_to.return_value = catalog.path_to.return_value[:1]
    catalog.schema_action_reason.return_value = "Protected TimescaleDB members"
    session = AsyncMock()
    with pytest.raises(ActionRefused, match="TimescaleDB"):
        await DescribeModel(session, catalog).download(["public"], {})
    catalog.schema_action_reason.assert_awaited_once_with("public")
    session.query.assert_not_awaited()


async def test_schema_mutations_refuse_before_any_rehearsal_or_ddl() -> None:
    catalog = _catalog(None)
    catalog.path_to.return_value = catalog.path_to.return_value[:1]
    catalog.schema_action_reason.return_value = "Protected TimescaleDB members"
    session = AsyncMock()
    with pytest.raises(ActionRefused, match="TimescaleDB"):
        await RenameSchema(session, catalog).perform("public", {"new_name": "renamed"})
    with pytest.raises(ActionRefused, match="TimescaleDB"):
        await DropSchema(session, catalog).perform("public", {"cascade": True})
    with pytest.raises(ActionRefused, match="TimescaleDB"):
        await DropSchema(session, catalog).preview("public", {"cascade": True})
    session.schema_change.assert_not_awaited()
    session.rehearse.assert_not_awaited()


@pytest.mark.parametrize("preview", [False, True])
async def test_ordinary_relation_cascade_checks_protected_dependencies(preview: bool) -> None:
    catalog = _catalog(None)
    catalog.cascade_reason.return_value = "This cascade affects TimescaleDB objects"
    session = AsyncMock()
    action = DropRelation(session, catalog)
    with pytest.raises(ActionRefused, match="TimescaleDB"):
        operation = action.preview_on_set if preview else action.perform_on_set
        await operation(["public.events"], {"cascade": True})
    catalog.cascade_reason.assert_awaited_once_with("public", "events")
    session.transaction.assert_not_called()
    session.rehearse.assert_not_awaited()
