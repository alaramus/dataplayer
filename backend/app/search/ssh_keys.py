"""SSH keys, found by name: the owner's only, as every key route answers (D146).

Here rather than with the keys: they are in `app.connectors`, below the
engine (D197). A hit carries the public half's facts, never the key.
"""

import uuid
from collections.abc import Sequence

from sqlmodel import col, select

from app.connectors.ssh_keys import SshKey
from app.core.translation import N_, say
from app.search.models import (
    Facts,
    Hit,
    Match,
    ObjectsPlace,
    ObjectTarget,
    ObjectType,
    target_key,
)
from app.search.providers import (
    Asked,
    Found,
    ProviderCell,
    best_of,
    name_match,
    ordered,
    recalled,
    text_match,
    uuids_of,
)

# Far above what one person holds; a bound so that the query is bounded too.
MAX_KEYS = 1000


class SshKeys:
    place = ObjectsPlace(provider="ssh_keys")
    title = N_("SSH keys")
    offered_to_agent = False
    recalls: frozenset[ObjectType] = frozenset({"ssh_key"})

    def cells(self) -> tuple[ProviderCell, ...]:
        return (ProviderCell(field="names", cost="instant"),)

    async def search(self, asked: Asked) -> Found:
        hits: list[Hit] = []
        for key in await _owned(asked):
            match = best_of(
                name_match(asked.words, key.name),
                text_match(asked.words, "details", f"{key.algorithm} · {key.fingerprint}"),
            )
            if match is not None:
                hits.append(_hit(key, match))
        return ordered(hits, asked.limit)

    async def recall(
        self, asked: Asked, object_type: ObjectType, ids: Sequence[str]
    ) -> list[Hit]:
        return [_hit(key, recalled(key.name)) for key in await _owned(asked, uuids_of(ids))]


async def _owned(asked: Asked, ids: list[uuid.UUID] | None = None) -> list[SshKey]:
    statement = select(SshKey).where(SshKey.owner_id == asked.user.id)
    if ids is not None:
        statement = statement.where(col(SshKey.id).in_(ids))
    rows = await asked.session.exec(statement.limit(MAX_KEYS))
    return list(rows.all())


def _hit(key: SshKey, match: Match) -> Hit:
    target = ObjectTarget(object_type="ssh_key", object_id=str(key.id))
    return Hit(
        key=target_key(target),
        target=target,
        title=key.name,
        detail=say("SSH key · {algorithm}", algorithm=key.algorithm),
        # No time it changed: a key is renamed in place, so when it was made
        # is not when it last changed.
        facts=Facts(kind="ssh_key"),
        match=match,
        open="ssh_key",
    )
