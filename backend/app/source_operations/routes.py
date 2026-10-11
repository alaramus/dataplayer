import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.adapters.operations import ProducesJob
from app.adapters.resources import ResourcesDep
from app.connectors.access import resolve, resolve_adapter
from app.connectors.action_lookup import (
    ActionRequest,
    acting_or_501,
    action_for_node,
    allowed_or_403,
    perform,
)
from app.core.db import SessionDep
from app.core.problems import Problem
from app.jobs import crud as job_crud
from app.jobs.models import JobPublic, public
from app.jobs.runner import JobRunnerDep
from app.realtime.topics import TopicsDep
from app.source_operations.handler import EXCLUSIVE_WITH, KIND, revision_of
from app.source_operations.models import SourceOperation, TargetRecord
from app.users.deps import CurrentUser

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.post(
    "/{connector_id}/actions/{action_name}/jobs", status_code=202, response_model=JobPublic,
)
async def start_action_job(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    runner: JobRunnerDep,
    topics: TopicsDep,
    connector_id: uuid.UUID,
    action_name: str,
    body: ActionRequest,
) -> Any:
    """
    Carry out a reviewed action as an owned job over the targets its plan fixes.

    The same lookup, availability and grant checks as running an action. The
    plan is drawn again and compared with the reviewed fingerprint before the
    job is written down, and the job is bound to the connection as it was read
    here. One such job at a time per connection, and none beside a restore
    (D123).
    """
    connector, _ = await resolve(session, connector_id, current_user, requires="read")
    revision = revision_of(connector)
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    action = await action_for_node(acting_or_501(adapter), action_name, body.node_id)
    allowed_or_403(action, access)
    if not isinstance(action, ProducesJob):
        raise HTTPException(
            status_code=415,
            detail={"message": f"{action.title} is not carried out as a job"},
        )
    fingerprint = body.reviewed_fingerprint
    if fingerprint is None:
        raise Problem(422, "actions.plan_not_reviewed")
    plan = await perform(lambda: action.plan_job(body.node_id, body.params, fingerprint))
    operation = SourceOperation(
        action=action.name,
        title=action.title,
        node_id=body.node_id,
        params=body.params,
        requires=action.requires,
        connector_revision=revision,
        summary=plan.summary,
        unit_fingerprint=plan.unit_fingerprint,
        targets=[TargetRecord(target=target) for target in plan.targets],
    )
    try:
        job = await job_crud.admit_exclusive(
            session,
            owner_id=current_user.id,
            kind=KIND,
            subject_id=connector_id,
            excluding=EXCLUSIVE_WITH,
            step_count=len(runner.steps_of(KIND)),
            parameters=operation.model_dump(mode="json"),
        )
    except job_crud.SubjectBusy as busy:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Another operation is already running on this connection",
                "job_id": str(busy.job_id),
            },
        )
    await runner.launch(job, topics)
    return public(job)
