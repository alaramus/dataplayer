"""A collection's definition, as the JSON the server keeps it in (D283).

MongoDB has no DDL. What answers "what is this, really" is what
`listCollections` says of it — its type, its options with the validator, a
view's source and pipeline — and, for a collection, its indexes as
`listIndexes` writes them. Relaxed Extended JSON, as everything else here.
"""

from typing import Any

from app.adapters import jsontext
from app.adapters.content import ContentRequest, ContentResult, JsonContent, json_tree
from app.adapters.mongodb.documents import read_documents
from app.adapters.mongodb.relation import MongodbRelation
from app.adapters.mongodb.reports import report_for
from app.adapters.mongodb.session import MongodbSession
from app.adapters.mongodb.values import relaxed_json
from app.core.translation import say


class MongodbContent:
    def __init__(self, session: MongodbSession, relation: MongodbRelation) -> None:
        self._session = session
        self._relation = relation

    async def read_content(self, request: ContentRequest) -> ContentResult:
        if request.representation == "jsonl":
            facts = await self._relation.facts(request.node_id, structure=False)
            return await read_documents(
                self._session, facts, limit=request.limit, offset=request.offset
            )
        report = report_for(request.node_id)
        if report is not None and request.representation == "json":
            # What the report runs, as it is written here.
            source = {
                "database": report.database,
                "collection": report.collection,
                "pipeline": list(report.pipeline),
            }
            return JsonContent(value=json_tree(jsontext.load(relaxed_json(source))))
        if request.representation != "json":
            raise ValueError(
                say(
                    'This MongoDB source does not offer the "{representation}" content representation',
                    representation=request.representation,
                )
            )
        facts = await self._relation.facts(request.node_id)
        definition: dict[str, Any] = {
            "name": facts.name,
            "type": facts.type,
            "options": facts.options,
        }
        if not facts.is_view:
            definition["indexes"] = facts.indexes
        return JsonContent(value=json_tree(jsontext.load(relaxed_json(definition))))
