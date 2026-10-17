"""What a name typed into a form must be before it can become an identifier.

One rule, because it is one rule: PostgreSQL allows 63 bytes for a name of any
kind, and a name that is empty or padded with spaces is a mistake whatever it
names. The things a form here asks the name of differ only in the word for what
is being named, so the rule is written once and each kind brings its two
sentences: whole, because a word passed into a sentence is not translated
(D226).

Refusing is not quoting. What a person did mean to type is made safe by
`psycopg.sql.Identifier`, which every caller still composes with; this only
turns away what nobody means.
"""

from collections.abc import Callable
from typing import Literal

from app.core.translation import N_, say

# PostgreSQL truncates rather than refuses beyond this, which is worse than a
# refusal: a name silently becomes another name.
NAME_LIMIT_BYTES = 63

NameSubject = Literal["relation", "schema", "role", "tablespace", "object", "column"]

# What is wrong with an empty name, and with a long one, for each kind.
_REFUSALS: dict[NameSubject, tuple[str, str]] = {
    "relation": (
        N_("A relation name cannot be empty or start or end with spaces"),
        N_("A PostgreSQL relation name cannot exceed {limit} bytes"),
    ),
    "schema": (
        N_("A schema name cannot be empty or start or end with spaces"),
        N_("A PostgreSQL schema name cannot exceed {limit} bytes"),
    ),
    "role": (
        N_("A role name cannot be empty or start or end with spaces"),
        N_("A PostgreSQL role name cannot exceed {limit} bytes"),
    ),
    "tablespace": (
        N_("A tablespace name cannot be empty or start or end with spaces"),
        N_("A PostgreSQL tablespace name cannot exceed {limit} bytes"),
    ),
    "object": (
        N_("An object name cannot be empty or start or end with spaces"),
        N_("A PostgreSQL object name cannot exceed {limit} bytes"),
    ),
    "column": (
        N_("A column name cannot be empty or start or end with spaces"),
        N_("A PostgreSQL column name cannot exceed {limit} bytes"),
    ),
}


def name_check(subject: NameSubject) -> Callable[[str], str]:
    """A field validator for the name of one kind of thing.

    A factory rather than a function taking two arguments, because Pydantic
    calls a field validator with the value alone.
    """
    empty, too_long = _REFUSALS[subject]

    def check(value: str) -> str:
        if value == "" or value != value.strip():
            raise ValueError(say(empty))
        if len(value.encode("utf-8")) > NAME_LIMIT_BYTES:
            raise ValueError(say(too_long, limit=NAME_LIMIT_BYTES))
        return value

    return check
