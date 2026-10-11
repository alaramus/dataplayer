"""A person's SSH keys: making one, bringing one, and opening a locked one (D146, D147).

A router of its own rather than routes under a connection: a key is its
owner's and serves every connection they point at it.
"""

import uuid
from typing import Any

from anyio import to_thread
from fastapi import APIRouter, HTTPException

from app.adapters.ssh import keys
from app.connectors import ssh_keys
from app.connectors.keyring import KEYRING
from app.connectors.ssh_keys import (
    SshKey,
    SshKeyGenerate,
    SshKeyImport,
    SshKeyPublic,
    SshKeyRename,
    SshKeyUnlock,
)
from app.core.db import SessionDep
from app.core.problems import Problem
from app.core.schemas import Message
from app.users.deps import CurrentUser

router = APIRouter(prefix="/ssh-keys", tags=["ssh-keys"])


@router.get("/", response_model=list[SshKeyPublic])
async def read_ssh_keys(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Every key of this person, with the connections that sign in with each.
    """
    rows = await ssh_keys.list_own(session, current_user.id)
    uses = await ssh_keys.uses(session, current_user.id)
    return [ssh_keys.public_of(row, uses.get(row.id, [])) for row in rows]


@router.post("/generate", response_model=SshKeyPublic)
async def generate_ssh_key(
    session: SessionDep, current_user: CurrentUser, body: SshKeyGenerate
) -> Any:
    """
    Make a key pair on this server. Its private half never leaves it.

    The public half comes back to be added to `authorized_keys` on the servers
    this key should open.
    """
    passphrase = ssh_keys.passphrase_of(body)
    # Off the event loop: an RSA key takes a second to make, and encrypting
    # one under a passphrase runs a deliberately slow derivation.
    prepared = await to_thread.run_sync(keys.generate, body.key_type, passphrase)
    row = await ssh_keys.create(
        session,
        owner_id=current_user.id,
        name=body.name,
        private_key=prepared.private_key,
        facts=prepared.facts,
        mode=ssh_keys.mode_of(body),
        passphrase=passphrase,
    )
    return ssh_keys.public_of(row, [])


@router.post("/import", response_model=SshKeyPublic)
async def import_ssh_key(
    session: SessionDep, current_user: CurrentUser, body: SshKeyImport
) -> Any:
    """
    Keep a key somebody already has.

    A key that arrives encrypted needs the passphrase that opens it; one that
    arrives in the clear is locked with the passphrase given, if any.
    """
    passphrase = ssh_keys.passphrase_of(body)
    try:
        prepared = await to_thread.run_sync(
            keys.imported, body.private_key.get_secret_value(), passphrase
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    row = await ssh_keys.create(
        session,
        owner_id=current_user.id,
        name=body.name,
        private_key=prepared.private_key,
        facts=prepared.facts,
        mode=ssh_keys.mode_of(body),
        passphrase=passphrase,
    )
    return ssh_keys.public_of(row, [])


@router.patch("/{key_id}", response_model=SshKeyPublic)
async def rename_ssh_key(
    session: SessionDep, current_user: CurrentUser, key_id: uuid.UUID, body: SshKeyRename
) -> Any:
    """
    Rename a key. Nothing else about one changes: a different key is a new one.
    """
    row = await _own_or_404(session, key_id, current_user.id)
    row.name = body.name.strip()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return await _public(session, row, current_user.id)


@router.delete("/{key_id}", response_model=Message)
async def delete_ssh_key(
    session: SessionDep, current_user: CurrentUser, key_id: uuid.UUID
) -> Any:
    """
    Delete a key no connection signs in with.

    Refused while one does, and the answer names them: deleting it would
    leave those connections unable to sign in, and which ones is exactly what
    a person needs to know to decide.
    """
    row = await _own_or_404(session, key_id, current_user.id)
    used_by = (await ssh_keys.uses(session, current_user.id)).get(row.id, [])
    if used_by:
        names = ", ".join(use.name for use in used_by)
        raise Problem(409, "ssh_keys.in_use", names=names)
    KEYRING.lock(row.id)
    await session.delete(row)
    await session.commit()
    return Message(message="Key deleted")


@router.post("/{key_id}/unlock", response_model=SshKeyPublic)
async def unlock_ssh_key(
    session: SessionDep, current_user: CurrentUser, key_id: uuid.UUID, body: SshKeyUnlock
) -> Any:
    """
    Hold the passphrase of a key that asks for one, in memory, for a while.

    Checked against the key before it is held, so a mistyped passphrase is
    said here rather than as a failed sign-in somewhere else later.
    """
    row = await _own_or_404(session, key_id, current_user.id)
    if row.passphrase_mode != "ask":
        raise Problem(409, "ssh_keys.no_passphrase")
    passphrase = body.passphrase.get_secret_value()
    try:
        await to_thread.run_sync(
            keys.facts_of, ssh_keys.private_key_of(row), passphrase
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    KEYRING.unlock(row.id, passphrase, seconds=body.minutes * 60)
    return await _public(session, row, current_user.id)


@router.post("/{key_id}/lock", response_model=SshKeyPublic)
async def lock_ssh_key(
    session: SessionDep, current_user: CurrentUser, key_id: uuid.UUID
) -> Any:
    """
    Forget the passphrase now rather than when its time is up.
    """
    row = await _own_or_404(session, key_id, current_user.id)
    KEYRING.lock(row.id)
    return await _public(session, row, current_user.id)


async def _own_or_404(
    session: SessionDep, key_id: uuid.UUID, owner_id: uuid.UUID
) -> SshKey:
    row = await ssh_keys.get_own(session, key_id, owner_id)
    if row is None:
        raise Problem(404, "ssh_keys.not_found")
    return row


async def _public(
    session: SessionDep, row: SshKey, owner_id: uuid.UUID
) -> SshKeyPublic:
    uses = await ssh_keys.uses(session, owner_id)
    return ssh_keys.public_of(row, uses.get(row.id, []))
