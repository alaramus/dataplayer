"""What a source's failure is reduced to, named once for every model carrying one.

Apart from `protocol.py` because a model that `protocol.py` itself imports — a
search result that stopped on a failure — has to name the kind too.
"""

from typing import Literal

# `locked` is not a refusal by the source: the key a connection signs in with
# asks for a passphrase nobody has given it lately, and giving it is the way
# on (D147). A kind of its own so a screen can offer exactly that.
ErrorKind = Literal["auth", "network", "timeout", "config", "locked", "unknown"]

# The kinds that say the server was not reached. Any other failure is an
# answer: a refused password or a locked key is fixed by its owner, and a
# server that gave it is not down.
UNANSWERED: frozenset[ErrorKind | None] = frozenset({"network", "timeout"})
