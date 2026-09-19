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


def layout(
    *,
    group: str = DEFAULT_GROUP,
    row: str | None = None,
    multiline: bool = False,
    purpose: str | None = None,
) -> JsonDict:
    """Fields sharing a `row` are laid out on one line, in declaration order.

    The row is named rather than numbered so that inserting a field between
    two others does not renumber everything after it.

    `multiline` says the value is written on several lines — the members of a
    Redis set, one per line — so the form gives it a box instead of a line.
    A statement about the field, made where the field is: the type is `str`
    either way, and a screen inferring "long" from "string" would give every
    host name six lines.

    `purpose` says what the value means when a box would not do — the id of
    one of the owner's SSH keys, the key a server proved itself with — so the
    form can offer the right control without knowing which source asked.
    """
    extra: JsonDict = {"group": group}
    if row is not None:
        extra["row"] = row
    if multiline:
        extra["x-ui-multiline"] = True
    if purpose is not None:
        extra["x-ui-purpose"] = purpose
    return extra
