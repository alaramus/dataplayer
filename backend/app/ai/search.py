"""Conversations, quick chats and chat projects, as the search finds them: by
title, the owner's only (D141, D204).

A title is ciphertext like everything said in a chat, so the newest
NEWEST_TITLES of each kind are decrypted on a worker thread under the search's
limiter and matched there. Messages are never searched: D141 has no transcript
search. An archived chat is out of the history, and out of the search too.

Handed to the search at assembly: the engine sits below the agent and imports
no feature (D197). The agent is never offered this provider (D133).
"""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from anyio import to_thread
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.content import opened
from app.ai.conversations import shown_title as conversation_title
from app.ai.models import ChatProject, Conversation
from app.ai.quick_chat import QuickConversation, shown_title
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
    name_match,
    ordered,
    recalled,
    uuids_of,
)

# D204's bound, per kind: titles are short, and this many decrypt in
# milliseconds.
NEWEST_TITLES = 500


@dataclass(frozen=True)
class _Sealed:
    object_type: ObjectType
    id: uuid.UUID
    title: bytes
    changed_at: datetime | None


class ChatTitles:
    place = ObjectsPlace(provider="conversations")
    title = N_("Conversations")
    # Never to the agent (D133).
    offered_to_agent = False
    recalls: frozenset[ObjectType] = frozenset({"conversation", "quick_chat", "project"})

    def cells(self) -> tuple[ProviderCell, ...]:
        return (ProviderCell(field="names", cost="instant"),)

    async def search(self, asked: Asked) -> Found:
        sealed: list[_Sealed] = []
        left_out = False
        for object_type in _KINDS:
            rows = await _newest(asked.session, asked.user.id, object_type)
            left_out = left_out or len(rows) > NEWEST_TITLES
            sealed.extend(rows[:NEWEST_TITLES])
        words = asked.words
        over = asked.bounds.over
        found, read_all = await to_thread.run_sync(
            lambda: _matching(sealed, lambda title: name_match(words, title), over),
            limiter=asked.bounds.limiter,
        )
        cut = ordered([_hit(row, title, match) for row, title, match in found], asked.limit)
        if not read_all or left_out:
            notice = (
                say("Stopped before every title was read")
                if not read_all
                else say("Only the newest {count} chats of each kind are searched", count=NEWEST_TITLES)
            )
            return Found(hits=cut.hits, complete=False, notice=notice, more=cut.more)
        return cut

    async def recall(
        self, asked: Asked, object_type: ObjectType, ids: Sequence[str]
    ) -> list[Hit]:
        wanted = uuids_of(ids)
        if not wanted:
            return []
        sealed = await _newest(asked.session, asked.user.id, object_type, wanted)
        found, _ = await to_thread.run_sync(
            lambda: _matching(sealed, recalled, lambda: False),
            limiter=asked.bounds.limiter,
        )
        return [_hit(row, title, match) for row, title, match in found]


async def _conversations(
    session: AsyncSession, owner_id: uuid.UUID, ids: list[uuid.UUID] | None, limit: int
) -> list[_Sealed]:
    statement = select(Conversation).where(
        Conversation.owner_id == owner_id, col(Conversation.archived).is_(False)
    )
    if ids is not None:
        statement = statement.where(col(Conversation.id).in_(ids))
    rows = await session.exec(
        statement.order_by(col(Conversation.updated_at).desc()).limit(limit)
    )
    return [_Sealed("conversation", row.id, row.title, row.updated_at) for row in rows.all()]


async def _quick_chats(
    session: AsyncSession, owner_id: uuid.UUID, ids: list[uuid.UUID] | None, limit: int
) -> list[_Sealed]:
    statement = select(QuickConversation).where(
        QuickConversation.owner_id == owner_id, col(QuickConversation.archived).is_(False)
    )
    if ids is not None:
        statement = statement.where(col(QuickConversation.id).in_(ids))
    rows = await session.exec(
        statement.order_by(col(QuickConversation.updated_at).desc()).limit(limit)
    )
    return [_Sealed("quick_chat", row.id, row.title, row.updated_at) for row in rows.all()]


async def _projects(
    session: AsyncSession, owner_id: uuid.UUID, ids: list[uuid.UUID] | None, limit: int
) -> list[_Sealed]:
    statement = select(ChatProject).where(ChatProject.owner_id == owner_id)
    if ids is not None:
        statement = statement.where(col(ChatProject.id).in_(ids))
    rows = await session.exec(
        statement.order_by(col(ChatProject.created_at).desc()).limit(limit)
    )
    # No time it changed: a project is renamed in place, so when it was made
    # is not when it last changed.
    return [_Sealed("project", row.id, row.name, None) for row in rows.all()]


def _as_stored(title: str) -> str:
    return title


@dataclass(frozen=True)
class _Kind:
    words: str
    # The person's own of this kind, newest first: the owner's rule is in it.
    owned: Callable[
        [AsyncSession, uuid.UUID, list[uuid.UUID] | None, int], Awaitable[list[_Sealed]]
    ]
    # The title as its own list shows it, so a chat is found by what is read.
    shown: Callable[[str], str] = _as_stored


_KINDS: dict[ObjectType, _Kind] = {
    "conversation": _Kind(N_("Conversation"), _conversations, conversation_title),
    "quick_chat": _Kind(N_("Quick chat"), _quick_chats, shown_title),
    "project": _Kind(N_("Chat project"), _projects),
}


async def _newest(
    session: AsyncSession,
    owner_id: uuid.UUID,
    object_type: ObjectType,
    ids: list[uuid.UUID] | None = None,
) -> list[_Sealed]:
    """One more than the bound, newest first, so leaving some out is known."""
    return await _KINDS[object_type].owned(session, owner_id, ids, NEWEST_TITLES + 1)


def _matching(
    sealed: Sequence[_Sealed],
    match_of: Callable[[str], Match | None],
    over: Callable[[], bool],
) -> tuple[list[tuple[_Sealed, str, Match]], bool]:
    """Each title opened and matched, and whether all were. Blocking: decrypts."""
    found: list[tuple[_Sealed, str, Match]] = []
    for row in sealed:
        if over():
            return found, False
        title = _KINDS[row.object_type].shown(opened(row.title))
        match = match_of(title)
        if match is not None:
            found.append((row, title, match))
    return found, True


def _hit(row: _Sealed, title: str, match: Match) -> Hit:
    target = ObjectTarget(object_type=row.object_type, object_id=str(row.id))
    return Hit(
        key=target_key(target),
        target=target,
        title=title,
        detail=say(_KINDS[row.object_type].words),
        facts=Facts(kind=row.object_type, changed_at=row.changed_at),
        match=match,
        open=row.object_type,
    )
