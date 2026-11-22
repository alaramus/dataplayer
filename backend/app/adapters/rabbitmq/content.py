"""The Management API's bounded JSON document (D295)."""

from app.adapters import jsontext
from app.adapters.content import JsonContent, json_tree
from app.core.translation import say

MAX_JSON_BYTES = 4 * 1024 * 1024


def json_document(body: bytes) -> JsonContent:
    """Keep the API's JSON as a tree only when its complete body fits the cap."""
    if len(body) > MAX_JSON_BYTES:
        return JsonContent(
            source_text=body[:MAX_JSON_BYTES].decode("utf-8", errors="ignore"),
            truncated=True,
            notice=say("This JSON document is larger than {mb} MB", mb=4),
        )
    source = body.decode("utf-8")
    return JsonContent(value=json_tree(jsontext.load(source)))
