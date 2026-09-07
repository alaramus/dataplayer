from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.catalog import SchemaNode, TableNode
from app.adapters.postgres.actions import (
    DescribeModel,
    DropRelation,
    MoveRelation,
    PostgresActions,
    RenameRelation,
)
from app.adapters.relation import RelationModel


def _catalog(reason: str | None) -> AsyncMock:
    catalog = AsyncMock()
    catalog.path_to.return_value = [
        SchemaNode(id="public", name="public", has_children=True),
        TableNode(id="public.events", name="events", has_children=False),
    ]
    catalog.relation_action_reason.return_value = reason
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


async def test_schema_model_export_refuses_a_protected_member() -> None:
    catalog = _catalog("TimescaleDB relations are read-only in this version")
    catalog.path_to.return_value = catalog.path_to.return_value[:1]
    with patch("app.adapters.postgres.actions.PostgresRelation") as relation_type:
        relation_type.return_value.relation_models = AsyncMock(
            return_value=[
                RelationModel(
                    node_id="public.events", name="events", kind="table"
                )
            ]
        )
        with pytest.raises(ActionRefused, match="TimescaleDB"):
            await DescribeModel(AsyncMock(), catalog).download(["public"], {})
    catalog.relation_action_reason.assert_awaited_once_with("public", "events")
