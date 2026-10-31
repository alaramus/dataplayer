"""Shell syntax read as driver calls, never run as JavaScript (D296).

Pure: text in, operations out, no connection anywhere. What is read is the part
of `mongosh` a query is written in — `db.c.find({…}).sort({…})`, `aggregate`,
the writes, the index and collection commands, `db.runCommand({…})`, `use` and
`show` — with values spelt the shell's way: unquoted keys, single quotes,
trailing commas, comments, regular expressions and the constructors
`ObjectId("…")`, `ISODate("…")`, `NumberLong(…)` and the rest. There are no
variables, functions or loops; those are the terminal's (D286).

A statement ends where its chain of calls does: at a semicolon, or where the
next token cannot continue it, so one statement a line needs no semicolon and a
`.sort()` on the next line still belongs to the `find` above it.
"""

import base64
import binascii
import math
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from bson import Decimal128, Int64, ObjectId, Regex, Timestamp
from bson.binary import Binary
from bson.max_key import MaxKey
from bson.min_key import MinKey

from app.adapters.query import PreparedScript, PreparedStatement, StatementClass
from app.core.translation import N_, say

TokenKind = Literal["name", "string", "number", "regex", "punct", "end"]


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str
    start: int
    end: int
    flags: str = ""

    def punct(self, char: str) -> bool:
        return self.kind == "punct" and self.text == char

    def word(self, text: str) -> bool:
        return self.kind == "name" and self.text == text


class ShellSyntaxError(Exception):
    """Why the text is not a statement this console reads, and where."""

    def __init__(self, message: str, position: int, **params: Any) -> None:
        super().__init__(message)
        self.message = message
        self.position = position
        self.params = params


_NUMBER = re.compile(r"0[xX][0-9a-fA-F]+|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_NAME_START = re.compile(r"[^\W\d]|\$", re.UNICODE)
_NAME = re.compile(r"(?:[^\W\d]|\$)(?:\w|\$)*", re.UNICODE)
_PUNCT = frozenset("{}[](),:;.-")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


class _Lexer:
    """Tokens one at a time, so a statement that fails stops only itself."""

    def __init__(self, text: str, position: int = 0) -> None:
        self.text = text
        self.position = position
        self._peeked: Token | None = None

    def peek(self) -> Token:
        if self._peeked is None:
            self._peeked = self._read()
        return self._peeked

    def next(self) -> Token:
        token = self.peek()
        self._peeked = None
        return token

    def expect(self, char: str) -> Token:
        token = self.next()
        if not token.punct(char):
            raise ShellSyntaxError(N_("{expected} is expected here"), token.start, expected=char)
        return token

    def rest_of_line(self) -> tuple[str, int]:
        """The raw text up to the end of the line, for `use` and `show`."""
        self._peeked = None
        text = self.text
        end = len(text)
        for stop in ("\n", ";", "//"):
            found = text.find(stop, self.position)
            if found != -1:
                end = min(end, found)
        piece = text[self.position : end]
        self.position = end
        return piece.strip(), end - (len(piece) - len(piece.rstrip()))

    def _skip(self) -> None:
        text = self.text
        while self.position < len(text):
            if text[self.position].isspace():
                self.position += 1
            elif text.startswith("//", self.position):
                newline = text.find("\n", self.position)
                self.position = len(text) if newline == -1 else newline
            elif text.startswith("/*", self.position):
                close = text.find("*/", self.position + 2)
                if close == -1:
                    raise ShellSyntaxError(N_("A comment is not closed"), self.position)
                self.position = close + 2
            else:
                return

    def _read(self) -> Token:
        self._skip()
        text = self.text
        start = self.position
        if start >= len(text):
            return Token("end", "", start, start)
        char = text[start]
        if char in "'\"`":
            return self._string(char)
        if char.isdigit():
            found = _NUMBER.match(text, start)
            assert found is not None  # a digit always starts a number
            self.position = found.end()
            return Token("number", found.group(), start, self.position)
        if char == "/":
            return self._regex()
        if _NAME_START.match(char):
            found = _NAME.match(text, start)
            assert found is not None  # the first character was matched above
            self.position = found.end()
            return Token("name", found.group(), start, self.position)
        if char in _PUNCT:
            self.position += 1
            return Token("punct", char, start, self.position)
        raise ShellSyntaxError(N_("{character} is not expected here"), start, character=char)

    def _string(self, quote: str) -> Token:
        text = self.text
        start = self.position
        index = start + 1
        out: list[str] = []
        while index < len(text):
            char = text[index]
            if char == quote:
                self.position = index + 1
                return Token("string", "".join(out), start, self.position)
            if char == "\n" and quote != "`":
                break
            if quote == "`" and text.startswith("${", index):
                raise ShellSyntaxError(
                    N_("A template string with substitutions is not read here"), index
                )
            if char == "\\":
                index += 1
                if index >= len(text):
                    break
                escaped = text[index]
                if escaped == "u":
                    index, char = self._unicode(index)
                elif escaped == "x":
                    digits = text[index + 1 : index + 3]
                    if not re.fullmatch(r"[0-9a-fA-F]{2}", digits):
                        raise ShellSyntaxError(N_("This escape is not complete"), index - 1)
                    char = chr(int(digits, 16))
                    index += 2
                elif escaped == "\n":
                    char = ""
                else:
                    char = _ESCAPES.get(escaped, escaped)
            out.append(char)
            index += 1
        raise ShellSyntaxError(N_("A string is not closed"), start)

    def _unicode(self, index: int) -> tuple[int, str]:
        text = self.text
        if text.startswith("{", index + 1):
            close = text.find("}", index + 2)
            digits = text[index + 2 : close] if close != -1 else ""
            end = close
        else:
            digits = text[index + 1 : index + 5]
            end = index + 4
        if not re.fullmatch(r"[0-9a-fA-F]{1,6}", digits) or int(digits, 16) > 0x10FFFF:
            raise ShellSyntaxError(N_("This escape is not complete"), index - 1)
        return end, chr(int(digits, 16))

    def _regex(self) -> Token:
        text = self.text
        start = self.position
        index = start + 1
        in_class = False
        while index < len(text):
            char = text[index]
            if char == "\n":
                break
            if char == "\\":
                index += 2
                continue
            if char == "[":
                in_class = True
            elif char == "]":
                in_class = False
            elif char == "/" and not in_class:
                if index == start + 1:
                    break
                flags = re.match(r"[a-z]*", text[index + 1 :])
                assert flags is not None  # `[a-z]*` matches the empty string
                self.position = index + 1 + flags.end()
                return Token("regex", text[start + 1 : index], start, self.position, flags.group())
            index += 1
        raise ShellSyntaxError(N_("A regular expression is not closed"), start)


# Values -----------------------------------------------------------------------


def _int32(value: Any, position: int) -> int:
    number = _integer(value, position)
    if not -(2**31) <= number < 2**31:
        raise ShellSyntaxError(N_("{value} does not fit in a 32-bit integer"), position, value=number)
    return number


def _integer(value: Any, position: int) -> int:
    if isinstance(value, bool):
        raise ShellSyntaxError(N_("A whole number is expected here"), position)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    raise ShellSyntaxError(N_("A whole number is expected here"), position)


def _moment(args: list[Any], position: int) -> datetime:
    if not args:
        return datetime.now(UTC)
    value = args[0]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value / 1000, UTC)
    if isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ShellSyntaxError(N_("{value} is not a date this console reads"), position, value=value) from None
        return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)
    raise ShellSyntaxError(N_("A date is given as text or as milliseconds"), position)


def _object_id(args: list[Any], position: int) -> ObjectId:
    if not args:
        return ObjectId()
    value = args[0]
    if not isinstance(value, str) or not ObjectId.is_valid(value):
        raise ShellSyntaxError(N_("An ObjectId is 24 hexadecimal digits"), position)
    return ObjectId(value)


def _decimal(args: list[Any], position: int) -> Decimal128:
    value = args[0] if args else "0"
    try:
        return Decimal128(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        raise ShellSyntaxError(N_("{value} is not a decimal number"), position, value=value) from None


def _uuid(args: list[Any], position: int) -> uuid.UUID:
    if not args:
        return uuid.uuid4()
    try:
        return uuid.UUID(str(args[0]))
    except ValueError:
        raise ShellSyntaxError(N_("{value} is not a UUID"), position, value=args[0]) from None


def _binary(args: list[Any], position: int) -> Binary:
    if len(args) != 2 or not isinstance(args[1], str):
        raise ShellSyntaxError(N_("BinData takes a subtype and base64 text"), position)
    try:
        return Binary(base64.b64decode(args[1], validate=True), _integer(args[0], position))
    except (binascii.Error, ValueError):
        raise ShellSyntaxError(N_("BinData takes a subtype and base64 text"), position) from None


def _timestamp(args: list[Any], position: int) -> Timestamp:
    if len(args) == 1 and isinstance(args[0], Mapping):
        args = [args[0].get("t", 0), args[0].get("i", 0)]
    if len(args) != 2:
        raise ShellSyntaxError(N_("A Timestamp takes seconds and an increment"), position)
    return Timestamp(_integer(args[0], position), _integer(args[1], position))


def _regex(args: list[Any], position: int) -> Regex[Any]:
    if not args or not isinstance(args[0], str):
        raise ShellSyntaxError(N_("RegExp takes a pattern as text"), position)
    return Regex(args[0], str(args[1]) if len(args) > 1 else "")


def _number(args: list[Any], position: int) -> float:
    try:
        return float(args[0]) if args else 0.0
    except (TypeError, ValueError):
        raise ShellSyntaxError(N_("A number is expected here"), position) from None


_CONSTRUCTORS: dict[str, Any] = {
    "ObjectId": _object_id,
    "ISODate": _moment,
    "Date": _moment,
    "NumberLong": lambda args, at: Int64(_integer(args[0] if args else 0, at)),
    "Long": lambda args, at: Int64(_integer(args[0] if args else 0, at)),
    "NumberInt": lambda args, at: _int32(args[0] if args else 0, at),
    "Int32": lambda args, at: _int32(args[0] if args else 0, at),
    "NumberDecimal": _decimal,
    "Decimal128": _decimal,
    "Double": _number,
    "UUID": _uuid,
    "BinData": _binary,
    "Timestamp": _timestamp,
    "MinKey": lambda args, at: MinKey(),
    "MaxKey": lambda args, at: MaxKey(),
    "RegExp": _regex,
}

_WORDS: dict[str, Any] = {
    "true": True,
    "false": False,
    "null": None,
    # The shell writes an undefined field as null.
    "undefined": None,
    "NaN": math.nan,
    "Infinity": math.inf,
}


def _number_of(token: Token) -> int | float:
    text = token.text
    if text[:2] in ("0x", "0X"):
        return int(text, 16)
    if re.fullmatch(r"\d+", text):
        return int(text)
    return float(text)


def _value(lexer: _Lexer) -> Any:
    token = lexer.next()
    if token.punct("{"):
        return _object(lexer)
    if token.punct("["):
        return _array(lexer)
    if token.kind == "string":
        return token.text
    if token.kind == "number":
        return _number_of(token)
    if token.kind == "regex":
        return Regex(token.text, token.flags)
    if token.punct("-"):
        following = lexer.next()
        if following.kind == "number":
            return -_number_of(following)
        if following.word("Infinity"):
            return -math.inf
        raise ShellSyntaxError(N_("A number is expected here"), following.start)
    if token.kind == "name":
        if token.text in _WORDS:
            return _WORDS[token.text]
        constructor = token
        if token.text == "new":
            constructor = lexer.next()
        build = _CONSTRUCTORS.get(constructor.text) if constructor.kind == "name" else None
        if build is None:
            raise ShellSyntaxError(
                N_("{name} is not a value this console reads; variables and functions belong to the terminal"),
                constructor.start,
                name=constructor.text,
            )
        if not lexer.peek().punct("("):
            raise ShellSyntaxError(N_("{expected} is expected here"), lexer.peek().start, expected="(")
        return build(_arguments(lexer), constructor.start)
    raise ShellSyntaxError(N_("A value is expected here"), token.start)


def _object(lexer: _Lexer) -> dict[str, Any]:
    found: dict[str, Any] = {}
    while True:
        key = lexer.next()
        if key.punct("}"):
            return found
        if key.kind not in ("name", "string", "number"):
            raise ShellSyntaxError(N_("A field name is expected here"), key.start)
        lexer.expect(":")
        found[key.text] = _value(lexer)
        after = lexer.next()
        if after.punct("}"):
            return found
        if not after.punct(","):
            raise ShellSyntaxError(N_("A comma or {close} is expected here"), after.start, close="}")


def _array(lexer: _Lexer) -> list[Any]:
    items: list[Any] = []
    while True:
        if lexer.peek().punct("]"):
            lexer.next()
            return items
        items.append(_value(lexer))
        after = lexer.next()
        if after.punct("]"):
            return items
        if not after.punct(","):
            raise ShellSyntaxError(N_("A comma or {close} is expected here"), after.start, close="]")


def _arguments(lexer: _Lexer) -> list[Any]:
    lexer.expect("(")
    args: list[Any] = []
    while True:
        if lexer.peek().punct(")"):
            lexer.next()
            return args
        args.append(_value(lexer))
        after = lexer.next()
        if after.punct(")"):
            return args
        if not after.punct(","):
            raise ShellSyntaxError(N_("A comma or {close} is expected here"), after.start, close=")")


# Statements -------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    name: str
    # None for a property, `db.orders`; a list for a call, `.find(…)`.
    args: list[Any] | None
    position: int


@dataclass(frozen=True)
class Operation:
    """One call on the driver, with every argument already a BSON value."""

    verb: str
    # None is the database the run is in (D296).
    database: str | None = None
    collection: str | None = None
    args: tuple[Any, ...] = ()
    # A cursor's modifiers, in the order they were written.
    cursor: tuple[tuple[str, tuple[Any, ...]], ...] = ()
    # The verbosity, when the call is to be explained rather than run.
    explain: str | None = None


@dataclass(frozen=True)
class Read:
    """One statement as the console prepares it, and what it would call."""

    statement: PreparedStatement
    operation: Operation | None = None


@dataclass(frozen=True)
class _Verb:
    kind: StatementClass
    least: int
    most: int
    # The cursor methods that may follow it.
    modifiers: frozenset[str] = field(default_factory=frozenset)


_FIND_CURSOR = frozenset(
    {
        "sort",
        "limit",
        "skip",
        "projection",
        "hint",
        "collation",
        "comment",
        "maxTimeMS",
        "batchSize",
        "allowDiskUse",
        "toArray",
        "pretty",
        "explain",
    }
)
_AGGREGATE_CURSOR = frozenset({"toArray", "pretty", "explain"})

_COLLECTION_VERBS: dict[str, _Verb] = {
    "find": _Verb("read", 0, 3, _FIND_CURSOR),
    "findOne": _Verb("read", 0, 3),
    "aggregate": _Verb("read", 0, 2, _AGGREGATE_CURSOR),
    "countDocuments": _Verb("read", 0, 2),
    "estimatedDocumentCount": _Verb("read", 0, 1),
    "distinct": _Verb("read", 1, 3),
    "getIndexes": _Verb("read", 0, 0),
    "insertOne": _Verb("dml", 1, 2),
    "insertMany": _Verb("dml", 1, 2),
    "updateOne": _Verb("dml", 2, 3),
    "updateMany": _Verb("dml", 2, 3),
    "replaceOne": _Verb("dml", 2, 3),
    "deleteOne": _Verb("dml", 1, 2),
    "deleteMany": _Verb("dml", 1, 2),
    "findOneAndUpdate": _Verb("dml", 2, 3),
    "findOneAndReplace": _Verb("dml", 2, 3),
    "findOneAndDelete": _Verb("dml", 1, 2),
    "createIndex": _Verb("ddl", 1, 2),
    "createIndexes": _Verb("ddl", 1, 2),
    "dropIndex": _Verb("ddl", 1, 1),
    "dropIndexes": _Verb("ddl", 0, 1),
    "drop": _Verb("ddl", 0, 1),
    "renameCollection": _Verb("ddl", 1, 2),
}

_DATABASE_VERBS: dict[str, _Verb] = {
    "runCommand": _Verb("read", 1, 2),
    "adminCommand": _Verb("read", 1, 1),
    "getCollectionNames": _Verb("read", 0, 1),
    "getCollectionInfos": _Verb("read", 0, 2),
    "stats": _Verb("read", 0, 1),
    "createCollection": _Verb("ddl", 1, 2),
    "createView": _Verb("ddl", 3, 4),
    "dropDatabase": _Verb("ddl", 0, 1),
}

# What `db.<name>` means when it is not a collection: a collection by one of
# these names is reached with `getCollection`.
DATABASE_METHODS = frozenset({*_DATABASE_VERBS, "getSiblingDB", "getCollection"})

# What the old shell called these, and what this console reads instead.
_OLD_SHELL = {
    "count": "countDocuments",
    "insert": "insertOne / insertMany",
    "update": "updateOne / updateMany",
    "remove": "deleteOne / deleteMany",
    "save": "replaceOne",
}

_EXPLAIN = ("queryPlanner", "executionStats", "allPlansExecution")

# A command is classed by its name, compared without case. What is not listed
# changes something nobody here can name, and is asked about every time.
_READ_COMMANDS = frozenset(
    name.lower()
    for name in (
        "ping",
        "buildInfo",
        "serverStatus",
        "dbStats",
        "collStats",
        "dataSize",
        "listCollections",
        "listDatabases",
        "listIndexes",
        "count",
        "distinct",
        "find",
        "aggregate",
        "explain",
        "hostInfo",
        "connectionStatus",
        "getCmdLineOpts",
        "getParameter",
        "getLog",
        "isMaster",
        "hello",
        "replSetGetStatus",
        "replSetGetConfig",
        "top",
        "currentOp",
        "dbHash",
        "listCommands",
        "whatsmyuri",
        "features",
        "getDefaultRWConcern",
        "connPoolStats",
        "lockInfo",
        "usersInfo",
        "rolesInfo",
    )
)
_WRITE_COMMANDS = frozenset({"insert", "update", "delete", "findandmodify"})
_MAINTENANCE_COMMANDS = frozenset({"compact", "validate", "reindex"})
_ACCOUNT_COMMANDS = frozenset(
    name.lower()
    for name in (
        "createUser",
        "updateUser",
        "dropUser",
        "dropAllUsersFromDatabase",
        "grantRolesToUser",
        "revokeRolesFromUser",
        "createRole",
        "updateRole",
        "dropRole",
        "dropAllRolesFromDatabase",
        "grantPrivilegesToRole",
        "revokePrivilegesFromRole",
        "grantRolesToRole",
        "revokeRolesFromRole",
        "logout",
        "authenticate",
        "saslStart",
        "saslContinue",
    )
)
_SERVER_COMMANDS = frozenset(
    name.lower()
    for name in (
        "shutdown",
        "fsync",
        "fsyncUnlock",
        "setParameter",
        "setFeatureCompatibilityVersion",
        "replSetInitiate",
        "replSetReconfig",
        "replSetStepDown",
        "replSetFreeze",
        "replSetMaintenance",
        "replSetSyncFrom",
        "logRotate",
        "startSession",
        "endSessions",
        "killAllSessions",
        "killAllSessionsByPattern",
        "killSessions",
        "commitTransaction",
        "abortTransaction",
        "getMore",
        "killCursors",
    )
)

_ACCOUNTS = N_("Users and roles are not administered from the query editor")
_SERVER = N_("{command} is not run from the query editor; the terminal runs it")


def command_name(command: Mapping[str, Any]) -> str:
    return next(iter(command), "")


def _writes(pipeline: list[Any]) -> str | None:
    """`$out` or `$merge`, when the pipeline ends by writing somewhere."""
    if pipeline and isinstance(pipeline[-1], Mapping):
        for stage in ("$out", "$merge"):
            if stage in pipeline[-1]:
                return stage
    return None


def _document(value: Any, position: int, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ShellSyntaxError(N_("{what}: a document is expected"), position, what=say(what))
    return value


def _documents(value: Any, position: int, what: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ShellSyntaxError(N_("{what}: a list of documents is expected"), position, what=say(what))
    return value


def _text(value: Any, position: int, what: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ShellSyntaxError(N_("{what}: a name in quotes is expected"), position, what=say(what))
    return value


def _check_collection_args(verb: str, args: list[Any], position: int) -> None:
    """The shape of each argument, so a wrong one is refused before anything runs."""
    if verb in ("find", "findOne", "countDocuments", "deleteOne", "deleteMany", "findOneAndDelete"):
        if args:
            _document(args[0], position, N_("Filter"))
    if verb in ("find", "findOne") and len(args) > 1:
        _document(args[1], position, N_("Projection"))
    if verb == "aggregate" and args:
        _documents(args[0], position, N_("Pipeline"))
    if verb == "distinct":
        _text(args[0], position, N_("Field"))
        if len(args) > 1:
            _document(args[1], position, N_("Filter"))
    if verb == "insertOne":
        _document(args[0], position, N_("Document"))
    if verb == "insertMany":
        _documents(args[0], position, N_("Documents"))
    if verb in ("updateOne", "updateMany", "findOneAndUpdate"):
        _document(args[0], position, N_("Filter"))
        if not isinstance(args[1], dict):
            _documents(args[1], position, N_("Update"))
    if verb in ("replaceOne", "findOneAndReplace"):
        _document(args[0], position, N_("Filter"))
        _document(args[1], position, N_("Replacement"))
    if verb == "createIndex":
        _document(args[0], position, N_("Index key"))
    if verb == "createIndexes":
        _documents(args[0], position, N_("Index keys"))
    if verb == "dropIndex" and not isinstance(args[0], (str, dict)):
        raise ShellSyntaxError(N_("An index is named or given by its key"), position)
    if verb == "renameCollection":
        _text(args[0], position, N_("New name"))
        if len(args) > 1 and not isinstance(args[1], bool):
            raise ShellSyntaxError(N_("renameCollection takes a new name and true to drop the target"), position)
        return
    last = _COLLECTION_VERBS[verb].most
    if len(args) == last and last > 1 and verb != "distinct":
        _document(args[-1], position, N_("Options"))


def _check_database_args(verb: str, args: list[Any], position: int) -> None:
    if verb in ("runCommand", "adminCommand"):
        if isinstance(args[0], str):
            return
        command = _document(args[0], position, N_("Command"))
        if not command:
            raise ShellSyntaxError(N_("The command is empty"), position)
    if verb == "getCollectionInfos" and args:
        _document(args[0], position, N_("Filter"))
    if verb in ("createCollection", "createView"):
        _text(args[0], position, N_("Collection"))
    if verb == "createView":
        _text(args[1], position, N_("Source"))
        _documents(args[2], position, N_("Pipeline"))


def _command_of(operation: Operation) -> dict[str, Any]:
    first = operation.args[0]
    return {first: 1} if isinstance(first, str) else first


def classify(operation: Operation) -> tuple[StatementClass, str | None]:
    """The class of one operation, and the console's refusal when it has one."""
    verb = operation.verb
    if operation.explain is not None or verb in ("use", "show"):
        return "read", None
    if verb == "aggregate":
        pipeline = list(operation.args[0]) if operation.args else []
        return ("dml" if _writes(pipeline) else "read"), None
    if verb in ("runCommand", "adminCommand"):
        command = _command_of(operation)
        name = command_name(command).lower()
        if name in _ACCOUNT_COMMANDS:
            return "unknown", say(_ACCOUNTS)
        if name in _SERVER_COMMANDS:
            return "unknown", say(_SERVER, command=command_name(command))
        if name == "aggregate":
            stages = command.get("pipeline")
            return ("dml" if isinstance(stages, list) and _writes(stages) else "read"), None
        if name in _READ_COMMANDS:
            return "read", None
        if name in _WRITE_COMMANDS:
            return "dml", None
        if name in _MAINTENANCE_COMMANDS:
            return "maintenance", None
        return "ddl", None
    verbs = _DATABASE_VERBS if operation.collection is None else _COLLECTION_VERBS
    return verbs[verb].kind, None


def _empty_filter(operation: Operation) -> bool:
    return not operation.args or operation.args[0] == {}


def risk_of(operation: Operation, kind: StatementClass) -> tuple[bool, bool]:
    """Whether to ask every time, and whether what it takes away is gone (D66)."""
    verb = operation.verb
    if kind == "read":
        return False, False
    if verb in ("drop", "dropDatabase", "dropIndex", "dropIndexes"):
        return True, True
    if verb == "renameCollection":
        dropping = len(operation.args) > 1 and operation.args[1] is True
        return dropping, dropping
    if verb == "aggregate":
        replacing = _writes(list(operation.args[0])) == "$out"
        return replacing, replacing
    if verb in ("updateMany", "deleteMany"):
        return _empty_filter(operation), False
    if verb in ("runCommand", "adminCommand"):
        return True, kind == "ddl"
    return False, False


def _interpret(steps: list[Step], start: int) -> Operation:
    database: str | None = None
    index = 0
    while index < len(steps) and steps[index].name == "getSiblingDB" and steps[index].args is not None:
        args = steps[index].args or []
        if len(args) != 1:
            raise ShellSyntaxError(N_("{method}: {count} arguments are expected"), steps[index].position, method="getSiblingDB", count=1)
        database = _text(args[0], steps[index].position, N_("Database"))
        index += 1
    if index == len(steps):
        raise ShellSyntaxError(N_("Name a collection or a method after db"), start)
    step = steps[index]
    if step.args is not None and step.name in _DATABASE_VERBS:
        verb = _DATABASE_VERBS[step.name]
        _arity(step, verb)
        _check_database_args(step.name, step.args, step.position)
        for after in steps[index + 1 :]:
            if after.name not in ("pretty", "toArray"):
                raise _unknown(after)
        return Operation(verb=step.name, database=database, args=tuple(step.args))
    if step.args is not None and step.name == "getCollection":
        if len(step.args) != 1:
            raise ShellSyntaxError(N_("{method}: {count} arguments are expected"), step.position, method="getCollection", count=1)
        collection = _text(step.args[0], step.position, N_("Collection"))
        index += 1
    elif step.args is None:
        names: list[str] = []
        while index < len(steps) and steps[index].args is None:
            names.append(steps[index].name)
            index += 1
        collection = ".".join(names)
    else:
        raise _unknown(step, database_level=True)
    explain: str | None = None
    if index < len(steps) and steps[index].name == "explain" and steps[index].args is not None:
        explain = _verbosity(steps[index])
        index += 1
    if index == len(steps):
        raise ShellSyntaxError(N_("Name a method after the collection"), steps[-1].position)
    call = steps[index]
    verb_spec = _COLLECTION_VERBS.get(call.name)
    if verb_spec is None or call.args is None:
        raise _unknown(call)
    if explain is not None and call.name not in ("find", "aggregate"):
        raise ShellSyntaxError(N_("Only find and aggregate are explained here"), call.position)
    _arity(call, verb_spec)
    _check_collection_args(call.name, call.args, call.position)
    cursor: list[tuple[str, tuple[Any, ...]]] = []
    for modifier in steps[index + 1 :]:
        if modifier.args is None or modifier.name not in verb_spec.modifiers:
            raise _unknown(modifier)
        if modifier.name == "explain":
            explain = _verbosity(modifier)
            continue
        cursor.append((modifier.name, tuple(modifier.args)))
    return Operation(
        verb=call.name,
        database=database,
        collection=collection,
        args=tuple(call.args),
        cursor=tuple(cursor),
        explain=explain,
    )


def _verbosity(step: Step) -> str:
    args = step.args or []
    if not args:
        return "queryPlanner"
    value = args[0]
    if value is True:
        return "allPlansExecution"
    if value is False:
        return "queryPlanner"
    if value not in _EXPLAIN:
        raise ShellSyntaxError(
            N_("Explain takes one of {choices}"), step.position, choices=", ".join(_EXPLAIN)
        )
    return str(value)


def _arity(step: Step, verb: _Verb) -> None:
    count = len(step.args or [])
    if verb.least <= count <= verb.most:
        return
    if verb.least == verb.most:
        raise ShellSyntaxError(
            N_("{method}: {count} arguments are expected"), step.position, method=step.name, count=verb.least
        )
    raise ShellSyntaxError(
        N_("{method}: {least} to {most} arguments are expected"),
        step.position,
        method=step.name,
        least=verb.least,
        most=verb.most,
    )


def _unknown(step: Step, *, database_level: bool = False) -> ShellSyntaxError:
    if step.name in _OLD_SHELL:
        return ShellSyntaxError(
            N_("{method} is the old shell's; this console reads {instead}"),
            step.position,
            method=step.name,
            instead=_OLD_SHELL[step.name],
        )
    return ShellSyntaxError(
        N_("{method} is not a method this console runs; the terminal runs the rest of mongosh"),
        step.position,
        method=f"db.{step.name}" if database_level else step.name,
    )


_SHOW = {
    "dbs": "databases",
    "databases": "databases",
    "collections": "collections",
    "tables": "collections",
}


def _statement(lexer: _Lexer) -> tuple[Operation, int]:
    """One statement from where the lexer stands, and where it ends."""
    first = lexer.next()
    if first.word("use") or first.word("show"):
        argument, end = lexer.rest_of_line()
        if first.text == "use":
            if not re.fullmatch(r"[^\s/\\.\"$*<>:|?]+", argument):
                raise ShellSyntaxError(N_("use is followed by a database name"), first.start)
            return Operation(verb="use", database=argument), end
        shown = _SHOW.get(argument)
        if shown is None:
            raise ShellSyntaxError(N_("show is followed by dbs or collections"), first.start)
        return Operation(verb="show", args=(shown,)), end
    if not first.word("db"):
        raise ShellSyntaxError(N_("A statement here starts with db, use or show"), first.start)
    steps: list[Step] = []
    end = first.end
    while True:
        token = lexer.peek()
        if token.punct("."):
            lexer.next()
            name = lexer.next()
            if name.kind != "name":
                raise ShellSyntaxError(N_("A name is expected after the dot"), name.start)
            end = name.end
            if lexer.peek().punct("("):
                args = _arguments(lexer)
                end = lexer.position
                steps.append(Step(name.text, args, name.start))
            else:
                steps.append(Step(name.text, None, name.start))
        elif token.punct("["):
            lexer.next()
            name = lexer.next()
            if name.kind != "string":
                raise ShellSyntaxError(N_("A collection name in quotes is expected here"), name.start)
            end = lexer.expect("]").end
            steps.append(Step(name.text, None, name.start))
        else:
            break
    return _interpret(steps, first.start), end


_STATEMENT_START = re.compile(r"^[ \t]*(?:db\b|use\s|show\s)", re.MULTILINE)


def read_script(text: str) -> list[Read]:
    """Every statement in the text, each read on its own.

    A statement that does not parse is kept, with its refusal, up to the next
    line that starts a statement, so one mistake does not hide the rest.
    """
    found: list[Read] = []
    lexer = _Lexer(text)
    while True:
        try:
            token = lexer.peek()
        except ShellSyntaxError as failure:
            end = _recover(text, failure.position)
            found.append(_refused(text, len(found), failure.position, end, failure))
            lexer = _Lexer(text, end)
            continue
        if token.kind == "end":
            return found
        if token.punct(";"):
            lexer.next()
            continue
        start = token.start
        try:
            operation, end = _statement(lexer)
            following = lexer.peek()
            if not (
                following.kind == "end"
                or following.punct(";")
                or following.word("db")
                or following.word("use")
                or following.word("show")
            ):
                raise ShellSyntaxError(N_("The statement should end here"), following.start)
        except ShellSyntaxError as failure:
            end = _recover(text, start)
            found.append(_refused(text, len(found), start, end, failure))
            lexer = _Lexer(text, end)
            continue
        found.append(_prepared(text, len(found), start, end, operation))


def _recover(text: str, start: int) -> int:
    line_end = text.find("\n", start)
    following = None if line_end == -1 else _STATEMENT_START.search(text, line_end + 1)
    end = len(text) if following is None else following.start()
    # Never empty, so the lexer that starts again from here moves on.
    return max(start + len(text[start:end].rstrip()), start + 1)


def _where(text: str, position: int) -> tuple[int, int]:
    before = text[:position]
    return before.count("\n") + 1, position - (before.rfind("\n") + 1) + 1


def _refused(text: str, ordinal: int, start: int, end: int, failure: ShellSyntaxError) -> Read:
    line, column = _where(text, failure.position)
    problem = say(failure.message, **failure.params)
    return Read(
        PreparedStatement(
            ordinal=ordinal,
            start=start,
            end=max(end, start),
            text=text[start : max(end, start)],
            kind="unknown",
            refused=say("{problem} (line {line}, column {column})", problem=problem, line=line, column=column),
        )
    )


def target_of(operation: Operation) -> list[str]:
    if operation.collection is None:
        return [] if operation.database is None else [operation.database]
    if operation.database is None:
        return [operation.collection]
    return [f"{operation.database}.{operation.collection}"]


def _prepared(text: str, ordinal: int, start: int, end: int, operation: Operation) -> Read:
    kind, refusal = classify(operation)
    risky, destructive = risk_of(operation, kind)
    return Read(
        PreparedStatement(
            ordinal=ordinal,
            start=start,
            end=end,
            text=text[start:end],
            kind=kind,
            risk="high" if risky else "low",
            destructive=destructive,
            refused=refusal,
            targets=target_of(operation),
        ),
        operation if refusal is None else None,
    )


def prepare(text: str) -> PreparedScript:
    return PreparedScript(statements=[read.statement for read in read_script(text)])

