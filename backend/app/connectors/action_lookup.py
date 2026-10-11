"""Which action a request names, and whether this caller may run it here.

Shared by the connector routes and by the route that turns an action into an
owned job, so an action cannot be admitted by one door and refused by another.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.adapters.actions import (
    Action,
    ActionOffers,
    ActionRefused,
    ExplainsActionAvailability,
    RefusalReason,
    SupportsActions,
    UnknownAction,
)
from app.adapters.protocol import AdapterError, DataAdapter, NodeNotFound
from app.core.access import Access, at_least
from app.core.problems import Problem, ProblemCode

# One code per level rather than the level as a parameter: a parameter is
# data, and "write" inside a translated sentence would stay English (D225).
ACTION_NEEDS: dict[Access, ProblemCode] = {
    "read": "actions.needs_read",
    "write": "actions.needs_write",
    "structure": "actions.needs_structure",
    "own": "actions.needs_own",
}


class ActionRequest(BaseModel):
    node_id: str | None = None
    params: dict[str, Any] = {}
    reviewed_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


# One status per reason for refusing, in one place. A conflict is not a failure
# of the source, so none of these is a 502.
REFUSAL_STATUS: dict[RefusalReason, int] = {
    "conflict": 409,
    "not_applicable": 422,
    "too_large": 413,
}


def acting_or_501(adapter: DataAdapter) -> SupportsActions:
    if not isinstance(adapter, SupportsActions):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support actions",
                "error_kind": "config",
            },
        )
    return adapter


async def available_or_422(
    adapter: SupportsActions, node_id: str | None
) -> ActionOffers:
    try:
        if isinstance(adapter, ExplainsActionAvailability):
            return await adapter.action_offers(node_id)
        return ActionOffers(await adapter.available(node_id))
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc


async def action_for_node(
    adapter: SupportsActions, action_name: str, node_id: str | None
) -> Action[Any]:
    """The action to perform, or the reason it may not be performed here.

    Applicability is decided by the same call that lists what a node offers,
    so what the client is shown and what the server allows cannot drift apart.
    """
    try:
        action = adapter.action(action_name)
    except UnknownAction as exc:
        raise Problem(404, "actions.unknown", name=action_name) from exc

    available = await available_or_422(adapter, node_id)
    if action.name not in {offered.name for offered in available.actions}:
        reason = available.reason_for(action.name)
        if not reason:
            raise Problem(422, "actions.not_for_node", action=action.title)
        raise HTTPException(status_code=422, detail={"message": reason})
    return action


def allowed_or_403(action: Action[Any], access: Access) -> None:
    """Whether this caller may run this action, asked after it resolved.

    A level cannot be checked at the door, because which one is needed is the
    action's own statement and the name has not been resolved yet. Answering
    404 for the name would be a different lie: the action exists.
    """
    if not at_least(access, action.requires):
        raise Problem(403, ACTION_NEEDS[action.requires], action=action.title)


async def perform[T](run: Callable[[], Awaitable[T]]) -> T:
    try:
        return await run()
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except ValidationError as exc:
        # ValidationError before ValueError on purpose: it is one of those, and
        # only it can say which field was wrong.
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "params", *error["loc"]],
                    "msg": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()
            ],
        ) from exc
    except ActionRefused as exc:
        raise HTTPException(
            status_code=REFUSAL_STATUS[exc.reason],
            detail={"message": exc.message, "reason": exc.reason},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc
