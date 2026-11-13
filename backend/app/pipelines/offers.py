"""What can go from one end of a pipeline's link into the other (D176, D178).

Two ticked rows are asked as the pair window asks them, with one tick each
side (D167). An end that is what a link makes is asked of as that link will
make it: each kind is handed the description in place of a node, the
chain's root read for its columns.
"""

import re
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.fetch import FetchColumn
from app.adapters.protocol import (
    AdapterError,
    DataAdapter,
    NodeNotFound,
    SupportsCreateRelation,
    SupportsOwnReader,
    SupportsReadingOn,
)
from app.adapters.reading_on import ReadingTerms
from app.adapters.resources import ResourceStore
from app.connectors.access import resolve_adapter
from app.connectors.paste.kinds import refused
from app.connectors.paste.models import (
    Foreseen,
    KeyedChoice,
    PairEnd,
    PasteColumn,
    PasteOffer,
    PastePair,
)
from app.connectors.paste.registry import KINDS, LINK_ONLY, READS_ON, short_of
from app.connectors.paste.rows import columns_of
from app.core.access import Access
from app.core.problems import Problem
from app.pipelines.models import Card, CardRow, LinkEnd, LinkRuns, PipelineContent
from app.pipelines.results import Foresight, by_label, root_of
from app.users.models import User


class LinkOffersRequest(BaseModel):
    """The two ends of a link that is being drawn, or is drawn."""

    model_config = ConfigDict(extra="forbid")

    source: LinkEnd
    target: LinkEnd


class LinkDefaults(BaseModel):
    """What a link drawn with an offer starts with, so it is ready to run
    without a window where the choices can be guessed (D364)."""

    runs: LinkRuns = "scheduled"
    name: str | None = None
    columns: list[PasteColumn] | None = None
    by_key: KeyedChoice | None = None


class LinkOffer(PasteOffer):
    defaults: LinkDefaults = Field(default_factory=LinkDefaults)


class LinkOffers(BaseModel):
    offers: list[LinkOffer]


# A message's JSON fields as a topic's columns name them (D306).
_FIELD = "value."
_NOT_A_NAME = re.compile(r"[^0-9A-Za-z_]+")


def table_name(label: str) -> str:
    """A table named after what it is made from: its extension dropped, and
    what is not a letter, a digit or an underscore made one underscore."""
    stem = re.sub(r"\.[^.]+$", "", label)
    named = _NOT_A_NAME.sub("_", stem).strip("_").lower()
    return named[:63] or "rows"


def key_column(columns: list[FetchColumn]) -> str | None:
    """A topic's key, else the first column."""
    found = next((column for column in columns if column.name == "key"), None)
    if found is not None:
        return found.name
    return columns[0].name if columns else None


def key_values(columns: list[FetchColumn], key: str | None) -> list[PasteColumn]:
    """A message's JSON fields as a hash, else its whole value as a string."""
    fields = [column for column in columns if column.name.startswith(_FIELD) and len(column.name) > len(_FIELD)]
    if fields:
        return [PasteColumn(source=column.name, target=column.name[len(_FIELD):]) for column in fields]
    value = next((column for column in columns if column.name == "value"), None) or next(
        (column for column in columns if column.name != key), None
    )
    if value is None:
        return []
    target = value.name[len(_FIELD):] if value.name.startswith(_FIELD) else value.name
    return [PasteColumn(source=value.name, target=target)]


async def _text_type(target: DataAdapter, place: str) -> str | None:
    """The type a new table's column takes before anybody chose: text."""
    if not isinstance(target, SupportsCreateRelation):
        return None
    try:
        options = await target.new_relation_options(place)
    except (AdapterError, NodeNotFound, ValueError):
        return None
    if not options.supported or not options.column_type_options:
        return None
    codes = [option.code for option in options.column_type_options]
    if options.text_type in codes:
        return options.text_type
    return "text" if "text" in codes else codes[0]


async def defaults_of(
    offer: PasteOffer, target: DataAdapter, target_at: PairEnd, label: str
) -> LinkDefaults:
    """The choices a link drawn with this offer starts with. Nothing is
    guessed for a target that is a result not made yet: its window asks."""
    runs: LinkRuns = "continuous" if offer.reads_on else "scheduled"
    usable = offer.available or offer.name_conflict
    if not usable:
        return LinkDefaults(runs=runs)
    if offer.workflow == "new-relation":
        name = None if offer.name_conflict else (offer.suggested_name or table_name(label))
        if not isinstance(target_at, str):
            return LinkDefaults(runs=runs, name=name)
        type_code = await _text_type(target, target_at)
        if type_code is None or not offer.source_columns:
            return LinkDefaults(runs=runs, name=name)
        return LinkDefaults(
            runs=runs,
            name=name,
            columns=[
                PasteColumn(source=column.name, target=column.name, type_code=type_code)
                for column in offer.source_columns
            ],
        )
    if offer.workflow == "into-relation":
        takes = {column.name for column in offer.target_columns if column.insertable}
        paired = [
            PasteColumn(source=column.name, target=column.name)
            for column in offer.source_columns
            if column.name in takes
        ]
        return LinkDefaults(runs=runs, columns=paired or None)
    if offer.workflow == "keyed":
        key = key_column(offer.source_columns)
        values = key_values(offer.source_columns, key)
        if key is None or not values:
            return LinkDefaults(runs=runs)
        return LinkDefaults(
            runs=runs,
            by_key=KeyedChoice(key_column=key, prefix=offer.suggested_name or ""),
            columns=values,
        )
    return LinkDefaults(runs=runs)


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

    def label(self, end: LinkEnd) -> str:
        """What an end is called on its own: a ticked row's label, or the
        name a result will be made under."""
        if end.made_by is not None:
            made = self._foresight.made(end.made_by)
            return made.name if made is not None else ""
        card = self._content.card(end.card_id)
        row = None if card is None else next((one for one in card.rows if one.node_id == end.node_id), None)
        return "" if row is None else row.label

    async def link_offers(self, source_end: LinkEnd, target_end: LinkEnd) -> list[LinkOffer]:
        """Every offer, each with what a link drawn with it starts with."""
        offers = await self.offers(source_end, target_end)
        target_card = self._content.card(target_end.card_id)
        target = None if target_card is None else await self.adapter(target_card)
        if target is None:
            return [LinkOffer(**offer.model_dump()) for offer in offers]
        target_at = await self._end(target_end)
        label = self.label(source_end)
        return [
            LinkOffer(**offer.model_dump(), defaults=await defaults_of(offer, target[0], target_at, label))
            for offer in offers
        ]

    async def offers(self, source_end: LinkEnd, target_end: LinkEnd) -> list[PasteOffer]:
        """Every kind the two connections serve, each with its answer."""
        source_card = self._content.card(source_end.card_id)
        target_card = self._content.card(target_end.card_id)
        if source_card is None or target_card is None:
            raise Problem(404, "pipelines.card_not_found")
        if not self._content.holds(source_end) or not self._content.holds(target_end):
            raise Problem(404, "pipelines.row_not_found")
        source = await self.adapter(source_card)
        target = await self.adapter(target_card)
        if source is None or target is None:
            return []
        source_at = await self._end(source_end)
        target_at = await self._end(target_end)
        # A node read on is offered no kind that would read it whole at every
        # run (D312).
        read_on = (
            isinstance(source[0], SupportsReadingOn)
            and isinstance(source_at, str)
            and source[0].reads_on(source_at)
        )
        terms = (
            await _terms(source[0], source_at)
            if read_on and isinstance(source_at, str)
            else None
        )
        answers: list[PasteOffer] = []
        for kind in (*KINDS, *LINK_ONLY):
            if not kind.pipelines or not kind.serves(source[0], target[0]):
                continue
            if read_on and kind.name in READS_ON.replaces:
                continue
            asked = len(answers)
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
            if read_on and kind in LINK_ONLY and len(answers) > asked:
                answers[-1] = answers[-1].model_copy(
                    update={"reads_on": True, "reading": terms}
                )
        return answers


async def _terms(source: DataAdapter, node_id: str) -> ReadingTerms | None:
    """What the link's form asks of a node read on (D337); none when the
    source cannot say, which the offer's own answer already tells."""
    if not isinstance(source, SupportsOwnReader):
        return None
    try:
        return await source.reading_terms(node_id)
    except (AdapterError, NodeNotFound, ValueError):
        return None
