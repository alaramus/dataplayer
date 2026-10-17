"""What a source's failure is reduced to, named once for every model carrying one.

Apart from `protocol.py` because a model that `protocol.py` itself imports — a
search result that stopped on a failure — has to name the kind too.
"""

from app.core.error_kind import ErrorKind as ErrorKind

# The kinds that say the server was not reached. Any other failure is an
# answer: a refused password or a locked key is fixed by its owner, and a
# server that gave it is not down.
UNANSWERED: frozenset[ErrorKind | None] = frozenset({"network", "timeout"})
