"""CQL text split into statements and each statement classed (D343).

A tokenizer of CQL's own lexical rules rather than a split on semicolons: a
semicolon inside a string (`'it''s;'`), a quoted name (`"a;b"`), a function
body (`$$ … ; … $$`) or a comment (`--`, `//`, `/* */`) ends nothing. A batch
is one statement from `BEGIN BATCH` to `APPLY BATCH`, the statements inside it
and their semicolons included, because the server applies it as one.

The class is read from the first words. What `cqlsh` adds on top of CQL —
`CONSISTENCY`, `TRACING`, `COPY`, `SOURCE` and the rest — is not CQL, and the
server would refuse it; it is refused here with the reason.
"""

import re
from dataclasses import dataclass

from app.adapters.query import PreparedScript, PreparedStatement, StatementClass
from app.core.translation import say


@dataclass(frozen=True)
class _Token:
    kind: str  # "word", "string", "name", "marker", "punct", "body"
    text: str
    start: int
    end: int


_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MARKER = re.compile(r":[A-Za-z_][A-Za-z0-9_]*|:\"(?:[^\"]|\"\")+\"")


def _tokens(text: str) -> list[_Token]:
    """Every token of the text, comments and whitespace left out."""
    tokens: list[_Token] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if text.startswith(("--", "//"), index):
            end = text.find("\n", index)
            index = length if end < 0 else end + 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = length if end < 0 else end + 2
            continue
        if char in ("'", '"'):
            end = index + 1
            while end < length:
                if text[end] == char:
                    if end + 1 < length and text[end + 1] == char:
                        end += 2
                        continue
                    break
                end += 1
            end = min(end + 1, length)
            tokens.append(
                _Token("string" if char == "'" else "name", text[index:end], index, end)
            )
            index = end
            continue
        if text.startswith("$$", index):
            end = text.find("$$", index + 2)
            end = length if end < 0 else end + 2
            tokens.append(_Token("body", text[index:end], index, end))
            index = end
            continue
        if char == ":":
            found = _MARKER.match(text, index)
            if found is not None:
                tokens.append(_Token("marker", found.group(), index, found.end()))
                index = found.end()
                continue
        found = _WORD.match(text, index)
        if found is not None:
            tokens.append(_Token("word", found.group(), index, found.end()))
            index = found.end()
            continue
        tokens.append(_Token("punct", char, index, index + 1))
        index += 1
    return tokens


def _words(tokens: list[_Token], count: int) -> list[str]:
    return [token.text.upper() for token in tokens[:count] if token.kind == "word"]


# What cqlsh does itself; the server has never heard of any of it.
_SHELL_COMMANDS = frozenset(
    {
        "CAPTURE",
        "CLEAR",
        "CLS",
        "CONSISTENCY",
        "COPY",
        "DEBUG",
        "EXIT",
        "EXPAND",
        "HELP",
        "LOGIN",
        "PAGING",
        "QUIT",
        "SERIAL",
        "SHOW",
        "SOURCE",
        "TRACING",
        "ELAPSED",
    }
)

_DESTRUCTIVE = frozenset({"DROP", "TRUNCATE"})


def _class_of(tokens: list[_Token]) -> tuple[StatementClass, str | None]:
    words = _words(tokens, 3)
    first = words[0] if words else ""
    if first in ("SELECT", "DESCRIBE", "DESC", "LIST"):
        return "read", None
    if first in ("INSERT", "UPDATE", "DELETE"):
        return "dml", None
    if first == "BEGIN" and "BATCH" in words:
        return "dml", None
    if first in ("CREATE", "ALTER", "DROP", "TRUNCATE", "GRANT", "REVOKE"):
        return "ddl", None
    if first == "USE":
        return "session", None
    if first in _SHELL_COMMANDS:
        return "unknown", say(
            "{command} is a cqlsh command, not CQL; run it in cqlsh in a terminal",
            command=first,
        )
    return "unknown", say("This is not a CQL statement this console runs")


def _parameters(tokens: list[_Token]) -> list[str]:
    names: list[str] = []
    for token in tokens:
        if token.kind != "marker":
            continue
        name = token.text[1:]
        if name.startswith('"'):
            name = name[1:-1].replace('""', '"')
        else:
            # An unquoted name is folded to lower case, as CQL folds every one.
            name = name.lower()
        if name not in names:
            names.append(name)
    return names


def _targets(tokens: list[_Token]) -> list[str]:
    """The names right after FROM, INTO, UPDATE, TABLE and their kin."""
    found: list[str] = []
    after = {"FROM", "INTO", "UPDATE", "TABLE", "VIEW", "KEYSPACE", "ON", "TYPE"}
    for index, token in enumerate(tokens[:-1]):
        if token.kind == "word" and token.text.upper() in after:
            name = _qualified(tokens, index + 1)
            if name and name.upper() not in ("IF",) and name not in found:
                found.append(name)
    return found


def _qualified(tokens: list[_Token], index: int) -> str:
    parts: list[str] = []
    while index < len(tokens) and tokens[index].kind in ("word", "name"):
        parts.append(tokens[index].text)
        if index + 1 < len(tokens) and tokens[index + 1].text == ".":
            index += 2
            continue
        break
    return ".".join(parts)


def _split(text: str) -> list[tuple[int, int, list[_Token]]]:
    """Each statement's place in the text and its tokens; a batch is one."""
    statements: list[tuple[int, int, list[_Token]]] = []
    current: list[_Token] = []
    in_batch = False
    for token in _tokens(text):
        if token.kind == "punct" and token.text == ";":
            if in_batch:
                current.append(token)
                continue
            if current:
                statements.append((current[0].start, current[-1].end, current))
            current = []
            continue
        current.append(token)
        words = _words(current, 3)
        if words[:1] == ["BEGIN"] and "BATCH" in words:
            in_batch = True
        if in_batch and len(current) >= 2:
            last_two = [item.text.upper() for item in current[-2:]]
            if last_two == ["APPLY", "BATCH"]:
                in_batch = False
    if current:
        statements.append((current[0].start, current[-1].end, current))
    return statements


def prepare(text: str) -> PreparedScript:
    statements: list[PreparedStatement] = []
    parameters: list[str] = []
    for ordinal, (start, end, tokens) in enumerate(_split(text)):
        kind, refused = _class_of(tokens)
        first = _words(tokens, 1)
        names = _parameters(tokens)
        parameters += [name for name in names if name not in parameters]
        destructive = bool(first) and first[0] in _DESTRUCTIVE
        statements.append(
            PreparedStatement(
                ordinal=ordinal,
                start=start,
                end=end,
                text=text[start:end],
                kind=kind,
                risk="high" if destructive else "low",
                destructive=destructive,
                refused=refused,
                parameters=names,
                targets=_targets(tokens),
            )
        )
    return PreparedScript(statements=statements, parameters=parameters)


def object_of(text: str) -> tuple[str, str, str | None, str | None]:
    """What a structure change names: its verb, its kind, its keyspace and its name.

    `("CREATE", "TABLE", "shop", "items")`; the keyspace is None when the
    statement leaves it to the session's, and the name is None for what could
    not be read.
    """
    tokens = _tokens(text)
    words = [
        token.text.upper() if token.kind == "word" else token.text for token in tokens
    ]
    if not words:
        return "", "", None, None
    verb = words[0]
    index = 1
    kind_words: list[str] = []
    while (
        index < len(tokens)
        and tokens[index].kind == "word"
        and words[index]
        in (
            "TABLE",
            "MATERIALIZED",
            "VIEW",
            "INDEX",
            "CUSTOM",
            "TYPE",
            "KEYSPACE",
            "SCHEMA",
            "FUNCTION",
            "AGGREGATE",
            "ROLE",
            "USER",
            "TRIGGER",
            "OR",
            "REPLACE",
            "COLUMNFAMILY",
        )
    ):
        kind_words.append(words[index])
        index += 1
    kind = " ".join(
        word for word in kind_words if word not in ("OR", "REPLACE", "CUSTOM")
    )
    if verb == "TRUNCATE" and not kind:
        kind = "TABLE"
    while index < len(tokens) and words[index] in ("IF", "NOT", "EXISTS"):
        index += 1
    if kind == "INDEX" and verb == "CREATE":
        # `CREATE INDEX [name] ON table (…)`: the table is what changes.
        while index < len(tokens) and words[index] != "ON":
            index += 1
        index += 1
    name = _qualified(tokens, index)
    if not name:
        return verb, kind, None, None
    parts = [_unquoted(part) for part in _name_parts(tokens, index)]
    if len(parts) == 2:
        return verb, kind, parts[0], parts[1]
    return verb, kind, None, parts[0]


def _name_parts(tokens: list[_Token], index: int) -> list[str]:
    parts: list[str] = []
    while index < len(tokens) and tokens[index].kind in ("word", "name"):
        parts.append(tokens[index].text)
        if index + 1 < len(tokens) and tokens[index + 1].text == ".":
            index += 2
            continue
        break
    return parts


def _unquoted(part: str) -> str:
    """A name as the server keeps it: a quoted one as written, a bare one folded."""
    if part.startswith('"') and part.endswith('"') and len(part) >= 2:
        return part[1:-1].replace('""', '"')
    return part.lower()
