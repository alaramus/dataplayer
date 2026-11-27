"""A person's cloud accounts: making one, changing it, testing it (D451, D452).

A router of its own, as SSH keys have: an account is its owner's and serves
every connection they point at it.
"""

import uuid
from typing import Any, cast

from fastapi import APIRouter

from app.adapters.cloud import AccountKind, issuer_for
from app.adapters.protocol import AdapterError
from app.connectors import cloud_accounts
from app.connectors.cloud_accounts import (
    CloudAccount,
    CloudAccountCreate,
    CloudAccountPublic,
    CloudAccountSchemas,
    CloudAccountTest,
    CloudAccountUpdate,
)
from app.core.db import SessionDep
from app.core.problems import Problem
from app.core.schemas import Message, get_datetime_utc
from app.core.translation import say
from app.users.deps import CurrentUser

router = APIRouter(prefix="/cloud-accounts", tags=["cloud-accounts"])


@router.get("/", response_model=list[CloudAccountPublic])
async def read_cloud_accounts(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Every account of this person, with the connections that use each.
    """
    rows = await cloud_accounts.list_own(session, current_user.id)
    uses = await cloud_accounts.uses(session, current_user.id)
    return [cloud_accounts.public_of(row, uses.get(row.id, [])) for row in rows]


@router.get("/schema", response_model=CloudAccountSchemas)
async def read_cloud_account_schema(current_user: CurrentUser) -> Any:
    """
    The kinds of account and the ways each signs in that this person may choose.

    A way that signs in as this server is absent unless the installation
    offers it and the person is a superuser (D452).
    """
    return cloud_accounts.schemas_for(current_user)


@router.post("/", response_model=CloudAccountPublic)
async def create_cloud_account(
    session: SessionDep, current_user: CurrentUser, body: CloudAccountCreate
) -> Any:
    """
    Keep an account. Its secrets are never sent back.
    """
    name = body.name.strip()
    if await cloud_accounts.name_taken(session, current_user.id, name):
        raise Problem(409, "cloud_accounts.name_taken", name=name)
    model = cloud_accounts.validated(body.settings, current_user)
    shown, hidden = cloud_accounts.split(model)
    row = CloudAccount(
        owner_id=current_user.id,
        name=name,
        kind=model.kind,
        method=model.method,
        settings=shown,
        secrets=hidden,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return cloud_accounts.public_of(row, [])


@router.patch("/{account_id}", response_model=CloudAccountPublic)
async def update_cloud_account(
    session: SessionDep,
    current_user: CurrentUser,
    account_id: uuid.UUID,
    body: CloudAccountUpdate,
) -> Any:
    """
    Rename an account or change how it signs in; it keeps its kind.

    Every change makes a new version, so nothing issued under the old settings
    is handed out again.
    """
    row = await _own_or_404(session, account_id, current_user.id)
    if body.name is not None:
        name = body.name.strip()
        if await cloud_accounts.name_taken(session, current_user.id, name, besides=row.id):
            raise Problem(409, "cloud_accounts.name_taken", name=name)
        row.name = name
    if body.settings is not None:
        filled = cloud_accounts.with_stored_secrets(row, body.settings)
        model = cloud_accounts.validated(filled, current_user)
        if model.kind != row.kind:
            raise Problem(422, "cloud_accounts.kind_fixed")
        row.method = model.method
        row.settings, row.secrets = cloud_accounts.split(model)
        row.version += 1
        cloud_accounts.ISSUED.forget(row.id)
    row.updated_at = get_datetime_utc()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return await _public(session, row, current_user.id)


@router.delete("/{account_id}", response_model=Message)
async def delete_cloud_account(
    session: SessionDep, current_user: CurrentUser, account_id: uuid.UUID
) -> Any:
    """
    Delete an account no connection uses.

    Refused while one does, and the answer names them.
    """
    row = await _own_or_404(session, account_id, current_user.id)
    used_by = (await cloud_accounts.uses(session, current_user.id)).get(row.id, [])
    if used_by:
        raise Problem(409, "cloud_accounts.in_use", names=", ".join(use.name for use in used_by))
    cloud_accounts.ISSUED.forget(row.id)
    await session.delete(row)
    await session.commit()
    return Message(message=say("Account deleted"))


@router.post("/{account_id}/test", response_model=CloudAccountTest)
async def test_cloud_account(
    session: SessionDep, current_user: CurrentUser, account_id: uuid.UUID
) -> Any:
    """
    Make the cheapest harmless call the account allows, and say what it found.

    A refusal is an answer here rather than an error: the account exists and
    the test ran.
    """
    row = await _own_or_404(session, account_id, current_user.id)
    kind = cast(AccountKind, row.kind)
    issuer = issuer_for(kind)
    if issuer is None:
        raise Problem(501, "cloud_accounts.untestable", error_kind="config")
    try:
        settings = cloud_accounts.settings_of(row)
        if settings.ambient and not cloud_accounts.ambient_offered(current_user):
            raise Problem(403, "cloud_accounts.ambient_off")
        message: str = await cloud_accounts.run_issuer(kind, row.name, issuer.test, settings)
    except AdapterError as failure:
        return CloudAccountTest(ok=False, message=failure.message)
    return CloudAccountTest(ok=True, message=message)


async def _own_or_404(
    session: SessionDep, account_id: uuid.UUID, owner_id: uuid.UUID
) -> CloudAccount:
    row = await cloud_accounts.get_own(session, account_id, owner_id)
    if row is None:
        raise Problem(404, "cloud_accounts.not_found")
    return row


async def _public(
    session: SessionDep, row: CloudAccount, owner_id: uuid.UUID
) -> CloudAccountPublic:
    uses = await cloud_accounts.uses(session, owner_id)
    return cloud_accounts.public_of(row, uses.get(row.id, []))
