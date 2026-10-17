"""A Redis address, written and read back.

The one place that knows the grammar, for the reason PostgreSQL's lives beside
its driver: an address composed in one place and parsed in another drifts, and
it drifts in the quoting first. Both the address shown for a finished
connection and the one shown while a form is still being typed come through
`compose_url`.

There is no library call to lean on here — redis-py parses a URL but will not
write one — so the grammar is stated once, and the tests exercise both
directions against each other.
"""

from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

from app.core.translation import say

SCHEME = "redis"
# The scheme for a TLS connection. Recognised so that pasting one gets an
# answer about what is missing rather than a silent plaintext connection.
TLS_SCHEME = "rediss"

DEFAULT_PORT = 6379
# Redis numbers its databases and ships with sixteen. The options model holds
# the same bound; it is repeated here because a pasted string is checked
# before it becomes options.
MAX_DATABASE = 15


def compose_url(*, host: str, port: int | None = None, database: int | None = None) -> str:
    """A Redis address, from as many of its parts as there are.

    Never the password. This string is shown on screen and pasted into other
    tools, and the one place that composes it is the one place already obliged
    to keep the password out of what a caller sees.

    A part that is not there is left out rather than written empty:
    `redis://cache:6379` is an address a person reads, and `redis://cache:/`
    is a puzzle.
    """
    authority = quote(host, safe="")
    if port is not None:
        authority += f":{port}"
    if database is None:
        return f"{SCHEME}://{authority}"
    return f"{SCHEME}://{authority}/{database}"


def compose_url_with_password(
    *, host: str, port: int | None, database: int | None, password: str
) -> str:
    """The same address with the password in it, for somebody to paste.

    Deliberately separate from `compose_url`, and named so that the one thing
    it does differently is the first thing read. Nothing shows this except the
    window that reveals a service's credentials once (D89); everything else
    composes the address without a secret in it.
    """
    if password == "":
        return compose_url(host=host, port=port, database=database)
    plain = compose_url(host=host, port=port, database=database)
    return plain.replace(f"{SCHEME}://", f"{SCHEME}://:{quote(password, safe='')}@", 1)


def options_from_url(url: str) -> dict[str, Any]:
    """A connection string taken apart into the fields of the form.

    The inverse of `compose_url`, and it lives beside it for that reason.
    Nothing is opened.

    Which way of connecting the string describes is inferred here, because it
    is the driver's inference to make: a string carrying a password is the
    password variant, and one without it is the other. A form that read that
    off the presence of a substring would be a second, weaker parser of the
    same string.
    """
    parsed = urlsplit(url.strip())
    if parsed.scheme == TLS_SCHEME:
        raise ValueError(say("This connection does not do TLS yet"))
    if parsed.scheme != SCHEME:
        raise ValueError(say("That is not a Redis connection string"))
    if not parsed.hostname:
        raise ValueError(say("The connection string names no host"))

    options: dict[str, Any] = {"host": parsed.hostname}
    try:
        port = parsed.port
    except ValueError:
        raise ValueError(say("The connection string names no usable port")) from None
    options["port"] = port if port is not None else DEFAULT_PORT
    options["database"] = _database_of(parsed.path, parsed.query)

    # Redis puts the password in the userinfo, with the user usually empty:
    # `redis://:secret@host`. A user is accepted and dropped — this source
    # connects with the default user, and refusing a string that names one
    # would refuse the strings most tools write.
    password = unquote(parsed.password) if parsed.password else ""
    if password:
        options["auth_method"] = "password"
        options["password"] = password
    else:
        options["auth_method"] = "no_auth"
    return options


def _database_of(path: str, query: str) -> int:
    """Which of the numbered databases, from the path or from `?db=`.

    Both spellings exist in the wild, and neither is more correct than the
    other. A path that is not a number is a mistake worth saying rather than
    quietly reading as zero.
    """
    written = path.lstrip("/")
    if written == "":
        written = (parse_qs(query).get("db") or [""])[0]
    if written == "":
        return 0
    try:
        database = int(written)
    except ValueError:
        raise ValueError(say("The connection string names no usable database")) from None
    if not 0 <= database <= MAX_DATABASE:
        raise ValueError(say("A database number is between 0 and {top}", top=MAX_DATABASE))
    return database
