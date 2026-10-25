"""Data skipping indexes of a ClickHouse table, made and dropped (D273).

An index is added and then materialized, so the parts already written are
indexed too rather than only what arrives afterwards; an index whose
materializing fails is dropped again. None is unique (D269), and the primary
key, shown as an index, is part of the table's definition and is not dropped.
"""

import re

from app.adapters.clickhouse.columns import alter, changeable_facts
from app.adapters.clickhouse.inspection import RelationFacts
from app.adapters.clickhouse.relation import ClickhouseRelation
from app.adapters.clickhouse.session import ClickhouseSession, ServerError
from app.adapters.clickhouse.sql import SQL, Identifier
from app.adapters.clickhouse.vocabulary import INDEX_METHODS
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexCreated,
    IndexDropped,
)
from app.core.translation import N_, say

# Rows a granule of the index covers, in granules of the table: ClickHouse's
# own default when GRANULARITY is not said.
GRANULARITY = 1
NAME_LIMIT = 60

INDEX_REFUSALS: dict[int, str] = {
    44: N_("The table already has an index of that name"),
    36: N_("The table has no index of that name"),
    # The type does not accept these columns: a set or a Bloom filter over a
    # map, a min-max over an array.
    43: N_("This kind of index cannot be made over these columns"),
}

_UNSAFE = re.compile(r"[^0-9A-Za-z_]+")


def _derived_name(facts: RelationFacts, columns: list[str]) -> str:
    """`<table>_<columns>_idx`, plain letters only, made unique on the table."""
    base = _UNSAFE.sub("_", "_".join([facts.name, *columns])).strip("_")[:NAME_LIMIT] or "index"
    taken = {index.name for index in facts.indexes}
    name = f"{base}_idx"
    number = 2
    while name in taken:
        name = f"{base}_idx{number}"
        number += 1
    return name


class ClickhouseIndexes:
    def __init__(self, session: ClickhouseSession, relation: ClickhouseRelation) -> None:
        self._session = session
        self._relation = relation

    async def _table(self, node_id: str) -> RelationFacts:
        return await changeable_facts(self._relation, node_id, structure=True)

    async def create_index(self, request: CreateIndexRequest) -> CreateIndexResult:
        facts = await self._table(request.node_id)
        names = {column.name for column in facts.columns}
        for column in request.columns:
            if column not in names:
                raise ValueError(say('Relation has no column "{column}"', column=column))
        method = INDEX_METHODS.get(request.method)
        if method is None:
            raise ValueError(say('Unknown index method "{code}"', code=request.method))
        if request.unique:
            raise ValueError(say("A ClickHouse index cannot be unique; no key of ClickHouse is"))
        name = _derived_name(facts, request.columns)
        index = Identifier(name)
        # The method is the vocabulary's own text, never a client's.
        await alter(
            self._session,
            facts,
            SQL("ADD INDEX {} ({}) TYPE ").format(
                index, SQL(", ").join(Identifier(column) for column in request.columns)
            )
            + SQL(method.sql + f" GRANULARITY {GRANULARITY}"),
            refusals=INDEX_REFUSALS,
        )
        try:
            await alter(
                self._session,
                facts,
                SQL("MATERIALIZE INDEX {}").format(index),
                refusals=INDEX_REFUSALS,
                passing=frozenset({341}),
            )
        except ServerError:
            await self._session.command(
                "KILL MUTATION WHERE database = {database:String} AND table = {table:String} "
                "AND NOT is_done SYNC",
                {"database": facts.schema, "table": facts.name},
            )
            await alter(self._session, facts, SQL("DROP INDEX {}").format(index))
            raise ValueError(say("The index could not be built over the rows already there")) from None
        return IndexCreated(name=name)

    async def drop_index(self, request: DropIndexRequest) -> IndexDropped:
        facts = await self._table(request.node_id)
        if request.name == "PRIMARY KEY":
            raise ValueError(say("The primary key is part of the table's definition"))
        if not any(index.name == request.name for index in facts.indexes):
            raise ValueError(say('Relation has no index "{name}"', name=request.name))
        await alter(
            self._session,
            facts,
            SQL("DROP INDEX {}").format(Identifier(request.name)),
            refusals=INDEX_REFUSALS,
        )
        return IndexDropped(name=request.name)
