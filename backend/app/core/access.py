"""What a user may do with a connection, as one ordered scale.

Every question the application asks about access has the same shape — is what
this user holds at least what this route needs — so the vocabulary is a total
order and the answer is one comparison. A table of rules per route would grow
with the routes and nothing would keep the two in step.

It lives in `core` because both sides need it: `connectors` resolves a level,
and an action in `adapters` declares the one it requires. Neither may import
the other.
"""

from typing import Final, Literal, get_args

# Weakest first. `own` is what the owner of a connection holds: it is on the
# scale because routes compare against it, and it is not in `Grant` because
# ownership is a column on the connector rather than a row somebody can be
# handed.
Access = Literal["read", "write", "structure", "own"]

# What may be given away.
Grant = Literal["read", "write", "structure"]

_RANK: Final[dict[Access, int]] = {
    "read": 0,
    "write": 1,
    "structure": 2,
    "own": 3,
}


def at_least(held: Access, required: Access) -> bool:
    """Whether `held` admits everything `required` does."""
    return _RANK[held] >= _RANK[required]


def ranked() -> tuple[Access, ...]:
    """The scale itself, weakest first.

    Read from the same dictionary the comparison uses, so a value added to
    `Access` without a rank cannot be silently ordered last.
    """
    return tuple(sorted(get_args(Access), key=lambda level: _RANK[level]))
