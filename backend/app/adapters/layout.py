"""Where a field goes in the window that edits it.

Declared by the model that declares the field, because it is a statement about
the fields: that a host and a port together are an address, and that both
belong on the connection tab. The screen cannot know that. Left to it, the rule
would be inferred — "a number is narrow, so it fits beside the thing above it"
— which is a rule about addresses living in a component that has never heard of
one.

It travels as `json_schema_extra`, so it reaches the client through the same
JSON Schema as the titles and the defaults, and needs no second channel.
"""

from pydantic.config import JsonDict

# The tab a field lands on when its model says nothing else. One tab is not a
# choice, so a window showing only this group draws no tab strip at all.
DEFAULT_GROUP = "general"


def layout(*, group: str = DEFAULT_GROUP, row: str | None = None) -> JsonDict:
    """Fields sharing a `row` are laid out on one line, in declaration order.

    The row is named rather than numbered so that inserting a field between
    two others does not renumber everything after it.
    """
    extra: JsonDict = {"group": group}
    if row is not None:
        extra["row"] = row
    return extra
