"""What can go from one end of a pipeline's link into the other (D176, D178).

Two ticked rows are asked as the pair window asks them, with one tick each
side (D167). An end that is what a link makes is asked of as that link will
make it: each kind is handed the description in place of a node, the
chain's root read for its columns.
"""

import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.protocol import DataAdapter
from app.adapters.resources import ResourceStore
from app.connectors.access import resolve_adapter
from app.connectors.paste.kinds import refused
from app.connectors.paste.models import Foreseen, PairEnd, PasteOffer, PastePair
from app.connectors.paste.registry import KINDS, short_of
from app.connectors.paste.rows import columns_of
from app.core.access import Access
from app.pipelines.models import Card, CardRow, LinkEnd, PipelineContent
from app.pipelines.results import Foresight, by_label, root_of
from app.users.models import User


class LinkOffersRequest(BaseModel):
    """The two ends of a link that is being drawn, or is drawn."""

    model_config = ConfigDict(extra="forbid")

    source: LinkEnd
    target: LinkEnd


class Asking:
    """One question or many about one pipeline, each end read at most once.

    `strict` answers a connection that cannot be read with the one door's
    refusal; otherwise it is left out, as a card that says so already.
    """

    def __init__(
        self,
        session: AsyncSession,
        user: User,
        resources: ResourceStore,
        content: PipelineContent,
        *,
        strict: bool,
    ) -> None:
        self._session = session
        self._user = user
        self._resources = resources
        self._content = content
        self._strict = strict
        self._adapters: dict[uuid.UUID, tuple[DataAdapter, Access] | None] = {}
        self._roots: dict[tuple[uuid.UUID, str | None], Foreseen] = {}
        self._foresight = Foresight(content, self._root)

    async def adapter(self, card: Card) -> tuple[DataAdapter, Access] | None:
        if card.connector_id not in self._adapters:
            try:
                self._adapters[card.connector_id] = await resolve_adapter(
                    self._session, card.connector_id, self._user, self._resources, requires="read"
                )
            except HTTPException:
                if self._strict:
                    raise
                self._adapters[card.connector_id] = None
        return self._adapters[card.connector_id]

    def _root(self, card: Card, row: CardRow) -> Foreseen:
        return self._roots.get((card.id, row.node_id)) or by_label(card, row)

    async def _read_root(self, end: LinkEnd) -> None:
        """The columns at the start of the chain through this end, read once."""
        found = root_of(self._content, end)
        if found is None:
            return
        card, row = found
        if (card.id, row.node_id) in self._roots:
            return
        described = by_label(card, row)
        adapter = await self.adapter(card)
        if adapter is not None and row.node_id is not None and described.kind != "folder":
            columns = await columns_of(adapter[0], [row.node_id])
            if not isinstance(columns, str):
                described = described.model_copy(update={"columns": columns})
        self._roots[(card.id, row.node_id)] = described

    async def _end(self, end: LinkEnd) -> PairEnd:
        if end.made_by is None:
            return end.node_id
        await self._read_root(end)
        return self._foresight.at(end)

    async def offers(self, source_end: LinkEnd, target_end: LinkEnd) -> list[PasteOffer]:
        """Every kind the two connections serve, each with its answer."""
        source_card = self._content.card(source_end.card_id)
        target_card = self._content.card(target_end.card_id)
        if source_card is None or target_card is None:
            raise HTTPException(404, detail={"message": "No such card"})
        if not self._content.holds(source_end) or not self._content.holds(target_end):
            raise HTTPException(404, detail={"message": "No such row"})
        source = await self.adapter(source_card)
        target = await self.adapter(target_card)
        if source is None or target is None:
            return []
        source_at = await self._end(source_end)
        target_at = await self._end(target_end)
        answers: list[PasteOffer] = []
        for kind in KINDS:
            if not kind.pipelines or not kind.serves(source[0], target[0]):
                continue
            short = short_of(kind, source[1], target[1])
            if short is not None:
                answers.append(short)
            elif source_at is None:
                answers.append(refused(kind, kind.needs))
            elif isinstance(source_at, Foreseen) or isinstance(target_at, Foreseen):
                answers.append(await kind.foresee(source[0], target[0], source_at, target_at))
            else:
                # The target row is the place and the table at once (D176).
                pair = PastePair(
                    source_connector_id=source_card.connector_id,
                    source_node_ids=[source_at],
                    mode=kind.mode,
                    destination_node_id=target_at,
                    target_node_id=target_at,
                )
                answers.append(await kind.offer(source[0], target[0], pair))
        return answers
