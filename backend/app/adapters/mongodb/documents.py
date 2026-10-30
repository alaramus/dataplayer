"""A collection's documents whole, a page at a time, as JSON lines (D287).

The grid shows a document as columns; this shows it as itself, every field
and every level, in relaxed Extended JSON. A document's text past a ceiling
is cut and said to be, as a line of a JSONL file is.
"""

from app.adapters import jsontext
from app.adapters.content import JsonLine, JsonLinesContent, json_tree
from app.adapters.mongodb.inspection import CollectionFacts
from app.adapters.mongodb.session import MongodbSession
from app.adapters.mongodb.values import relaxed_json
from app.core.translation import say

# The most of one document drawn as a tree; a larger one is shown as the
# beginning of its text.
MAX_DOCUMENT_BYTES = 256 * 1024


def document_line(number: int, text: str) -> JsonLine:
    encoded = text.encode()
    if len(encoded) > MAX_DOCUMENT_BYTES:
        return JsonLine(
            line_number=number,
            source_text=encoded[:MAX_DOCUMENT_BYTES].decode(errors="ignore"),
            truncated=True,
            notice=say("This document is larger than 256 KB; only its beginning is shown."),
        )
    return JsonLine(line_number=number, value=json_tree(jsontext.load(text)))


async def read_documents(
    session: MongodbSession, facts: CollectionFacts, *, limit: int, offset: int
) -> JsonLinesContent:
    async with session.client() as client:
        with session.failures():
            cursor = client[facts.database][facts.name].find()
            if not facts.is_view:
                cursor = cursor.sort("_id", 1)
            documents = await cursor.skip(offset).limit(limit + 1).to_list()
    return JsonLinesContent(
        items=[
            document_line(offset + index + 1, relaxed_json(document))
            for index, document in enumerate(documents[:limit])
        ],
        has_more=len(documents) > limit,
        offset=offset,
    )
